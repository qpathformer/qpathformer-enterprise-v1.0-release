#!/usr/bin/env python3
"""
Q-Pathformer v0.9-3S (reference, sparse e08) — cleaned baseline prototype.

This reference baseline is the repaired and normalized e08 branch for
controlled benchmarking against:
- grouped_sparse_e64 (enterprise target)
- fused_sparse_e144 (strategic target)

Key goals
---------
- preserve the three-state scheduler design
- preserve the expert superposition path
- preserve the same high-level interface as e64/e144
- provide a clean, importable, instantiable reference baseline
- avoid duplicate class definitions and missing block references
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Callable, Dict, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


# -----------------------------------------------------------------------------
# Agent Registry
# -----------------------------------------------------------------------------
class AgentRegistry:
    """Registry for agent functions (multimodal handlers)."""
    _registry: Dict[str, Callable[[torch.Tensor], torch.Tensor]] = {}

    @classmethod
    def register(cls, name: str, fn: Callable[[torch.Tensor], torch.Tensor]) -> None:
        if name in cls._registry:
            raise ValueError(f"Agent '{name}' is already registered")
        cls._registry[name] = fn

    @classmethod
    def get(cls, name: str) -> Callable[[torch.Tensor], torch.Tensor]:
        if name not in cls._registry:
            raise KeyError(f"Agent '{name}' is not registered")
        return cls._registry[name]


# -----------------------------------------------------------------------------
# Three-State Scheduler
# -----------------------------------------------------------------------------
class ThreeStateScheduler(nn.Module):
    """Produces per-token path probabilities (dense, superposition, agent)."""

    def __init__(self, embed_dim: int, temperature: float = 1.0, min_agent_p: float = 0.0):
        super().__init__()
        self.linear = nn.Linear(embed_dim, 3)
        self.temperature = temperature
        self.min_agent_p = min_agent_p

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        logits = self.linear(x) / self.temperature
        probs = F.softmax(logits, dim=-1)

        if self.min_agent_p > 0:
            agent = probs[..., 2]
            floor = torch.full_like(agent, self.min_agent_p)
            agent = torch.maximum(agent, floor)
            other = probs[..., :2]
            s = agent + other.sum(dim=-1)
            probs = torch.cat(
                [other / s.unsqueeze(-1), agent.unsqueeze(-1) / s.unsqueeze(-1)],
                dim=-1,
            )
        return probs

    def router_aux_loss(self, probs: torch.Tensor, target_dist: torch.Tensor = None) -> torch.Tensor:
        avg_usage = probs.mean(dim=(0, 1))
        if target_dist is None:
            target_dist = torch.full_like(avg_usage, 1.0 / avg_usage.numel())
        eps = 1e-8
        avg_usage = avg_usage + eps
        target_dist = target_dist + eps
        return F.kl_div(avg_usage.log(), target_dist, reduction="batchmean")


# -----------------------------------------------------------------------------
# Feed-Forward (Dense Path)
# -----------------------------------------------------------------------------
class FeedForward(nn.Module):
    def __init__(self, embed_dim: int, hidden_dim: Optional[int] = None):
        super().__init__()
        hidden_dim = hidden_dim or 4 * embed_dim
        self.linear1 = nn.Linear(embed_dim, hidden_dim)
        self.linear2 = nn.Linear(hidden_dim, embed_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.linear2(F.gelu(self.linear1(x)))


# -----------------------------------------------------------------------------
# Reference Superposition Gate (8 experts)
# -----------------------------------------------------------------------------
class SuperpositionGate(nn.Module):
    """Simple readable expert gate for the e08 baseline.

    This keeps the reference branch intentionally easy to inspect.
    It uses per-expert FeedForward modules and top-k routing.
    """

    def __init__(self, embed_dim: int, num_experts: int = 8, k: int = 2, hidden_dim: Optional[int] = None):
        super().__init__()
        self.num_experts = num_experts
        self.k = k
        self.experts = nn.ModuleList([FeedForward(embed_dim, hidden_dim) for _ in range(num_experts)])

    def forward(self, x: torch.Tensor, gate_weights: torch.Tensor) -> torch.Tensor:
        bsz, seq_len, dim = x.shape
        e = self.num_experts

        topk_vals, topk_idx = torch.topk(gate_weights, self.k, dim=-1)
        topk_w = F.softmax(topk_vals, dim=-1)

        bt = bsz * seq_len
        x_flat = x.reshape(bt, dim)
        idx_flat = topk_idx.reshape(bt, self.k)
        w_flat = topk_w.reshape(bt, self.k)

        packed_positions = [[] for _ in range(e)]
        packed_weights = [[] for _ in range(e)]

        for slot in range(self.k):
            expert_ids_slot = idx_flat[:, slot]
            weights_slot = w_flat[:, slot]
            for expert_id in range(e):
                mask = expert_ids_slot == expert_id
                if mask.any():
                    pos = torch.nonzero(mask, as_tuple=False).squeeze(-1)
                    packed_positions[expert_id].append(pos)
                    packed_weights[expert_id].append(weights_slot[pos])

        out_flat = torch.zeros(bt, dim, device=x.device, dtype=x.dtype)
        for expert_id in range(e):
            if not packed_positions[expert_id]:
                continue
            pos_e = torch.cat(packed_positions[expert_id], dim=0)
            w_e = torch.cat(packed_weights[expert_id], dim=0).unsqueeze(-1)
            x_e = x_flat.index_select(0, pos_e)
            y_e = self.experts[expert_id](x_e)
            out_flat.index_add_(0, pos_e, y_e * w_e)

        return out_flat.view(bsz, seq_len, dim)

    def router_aux_loss(self, expert_logits: torch.Tensor, target_util: torch.Tensor = None) -> torch.Tensor:
        probs = torch.softmax(expert_logits, dim=-1)
        avg_util = probs.mean(dim=(0, 1))
        if target_util is None:
            target_util = torch.full_like(avg_util, 1.0 / avg_util.numel())
        eps = 1e-8
        avg_util = avg_util + eps
        target_util = target_util + eps
        return F.kl_div(avg_util.log(), target_util, reduction="batchmean")


# -----------------------------------------------------------------------------
# QPathformer Block
# -----------------------------------------------------------------------------
class QPathformerBlock(nn.Module):
    def __init__(self, embed_dim: int, num_heads: int, num_experts: int, k: int, agent_name: str = "default"):
        super().__init__()
        self.attention = nn.MultiheadAttention(embed_dim, num_heads, batch_first=True)
        self.attn_norm = nn.LayerNorm(embed_dim)
        self.dense_ff = FeedForward(embed_dim)
        self.super_ff = SuperpositionGate(embed_dim, num_experts=num_experts, k=k)

        if "default" not in AgentRegistry._registry:
            AgentRegistry.register("default", nn.Linear(embed_dim, embed_dim))
        self.agent_name = agent_name

        self.scheduler = ThreeStateScheduler(embed_dim)
        self.expert_gate = nn.Linear(embed_dim, num_experts)
        self.ff_norm = nn.LayerNorm(embed_dim)

    def forward(self, x: torch.Tensor):
        attn_out, _ = self.attention(x, x, x)
        x = self.attn_norm(x + attn_out)

        path_probs = self.scheduler(x)
        dense_prob = path_probs[..., 0].unsqueeze(-1)
        super_prob = path_probs[..., 1].unsqueeze(-1)
        agent_prob = path_probs[..., 2].unsqueeze(-1)

        dense_out = self.dense_ff(x)
        expert_logits = self.expert_gate(x)
        expert_weights = F.softmax(expert_logits, dim=-1)
        super_out = self.super_ff(x, expert_weights)

        agent_fn = AgentRegistry.get(self.agent_name)
        agent_out = agent_fn(x)

        ff_out = dense_prob * dense_out + super_prob * super_out + agent_prob * agent_out
        out = self.ff_norm(x + ff_out)

        return out, path_probs, expert_logits


# -----------------------------------------------------------------------------
# QPathformer Model
# -----------------------------------------------------------------------------
class QPathformer(nn.Module):
    """Reference e08 Q-Pathformer model."""

    def __init__(
        self,
        vocab_size: int,
        embed_dim: int,
        num_heads: int,
        num_layers: int,
        num_experts: int,
        k: int,
        max_seq_len: int,
        num_classes: Optional[int] = None,
        agent_name: str = "default",
    ):
        super().__init__()
        self.token_embed = nn.Embedding(vocab_size, embed_dim)
        self.pos_embed = self._init_positional_encoding(max_seq_len, embed_dim)
        self.layers = nn.ModuleList([
            QPathformerBlock(embed_dim, num_heads, num_experts, k, agent_name=agent_name)
            for _ in range(num_layers)
        ])
        self.num_classes = num_classes
        self.out_proj = nn.Linear(embed_dim, num_classes if num_classes is not None else vocab_size)

    def _init_positional_encoding(self, max_len: int, d_model: int) -> nn.Parameter:
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        return nn.Parameter(pe, requires_grad=False)

    def forward(self, input_ids: torch.Tensor):
        seq_len = input_ids.size(1)
        if seq_len > self.pos_embed.size(0):
            raise ValueError(f"Sequence length {seq_len} exceeds maximum {self.pos_embed.size(0)}")

        pos_embed = self.pos_embed[:seq_len, :].to(input_ids.device)
        x = self.token_embed(input_ids) + pos_embed

        all_path_probs, all_expert_logits = [], []
        for layer in self.layers:
            x, path_probs, expert_logits = layer(x)
            all_path_probs.append(path_probs)
            all_expert_logits.append(expert_logits)

        logits = self.out_proj(x)
        return logits, all_path_probs, all_expert_logits


# -----------------------------------------------------------------------------
# Training utilities
# -----------------------------------------------------------------------------
def train_qpathformer(
    model: QPathformer,
    data_loader: torch.utils.data.DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
    epochs: int = 1,
    alpha_path: float = 0.01,
    alpha_expert: float = 0.01,
    run_id: str = "default_run",
) -> dict:
    model.to(device)
    model.train()

    manifest = {"run_id": run_id, "epochs": []}

    for epoch in range(epochs):
        total_main_loss, total_tokens = 0.0, 0
        total_path_loss, total_expert_loss = 0.0, 0.0
        last_path_probs, last_expert_logits = None, None

        for input_ids, labels in data_loader:
            input_ids, labels = input_ids.to(device), labels.to(device)
            optimizer.zero_grad()

            logits, all_path_probs, all_expert_logits = model(input_ids)
            last_path_probs, last_expert_logits = all_path_probs, all_expert_logits

            vocab_size = logits.size(-1)
            loss_main = criterion(logits.view(-1, vocab_size), labels.view(-1))

            loss_path_router = sum(
                layer.scheduler.router_aux_loss(p)
                for layer, p in zip(model.layers, all_path_probs)
            )
            loss_expert_router = sum(
                layer.super_ff.router_aux_loss(e)
                for layer, e in zip(model.layers, all_expert_logits)
            )

            loss = loss_main + alpha_path * loss_path_router + alpha_expert * loss_expert_router
            loss.backward()
            optimizer.step()

            total_main_loss += loss_main.item() * input_ids.numel()
            total_tokens += input_ids.numel()
            total_path_loss += loss_path_router.item()
            total_expert_loss += loss_expert_router.item()

        avg_main_loss = total_main_loss / total_tokens if total_tokens > 0 else float("nan")

        epoch_entry = {
            "epoch": epoch + 1,
            "loss_main": avg_main_loss,
            "loss_path": total_path_loss,
            "loss_expert": total_expert_loss,
            "path_usage": {},
            "expert_usage": {},
        }

        if last_path_probs is not None and last_expert_logits is not None:
            for i, path_probs in enumerate(last_path_probs):
                avg_usage = path_probs.mean(dim=(0, 1)).detach().cpu().tolist()
                epoch_entry["path_usage"][f"block_{i}"] = {
                    "dense": avg_usage[0],
                    "super": avg_usage[1],
                    "agent": avg_usage[2],
                }

            for i, expert_logits in enumerate(last_expert_logits):
                probs = torch.softmax(expert_logits, dim=-1)
                avg_util = probs.mean(dim=(0, 1)).detach().cpu().tolist()
                epoch_entry["expert_usage"][f"block_{i}"] = {
                    f"expert_{j}": avg_util[j] for j in range(len(avg_util))
                }

        manifest["epochs"].append(epoch_entry)

    return manifest


# -----------------------------------------------------------------------------
# JSON save helper
# -----------------------------------------------------------------------------
def save_manifest(manifest: dict, out_dir: str = "manifests"):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    run_id = manifest.get("run_id", "default_run")
    out_path = Path(out_dir) / f"{run_id}_utilization.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[Audit] Saved cumulative utilization manifest to {out_path}")


if __name__ == "__main__":
    vocab_size = 5000
    embed_dim = 256
    num_heads = 8
    num_layers = 4
    num_experts = 8
    k = 2
    max_seq_len = 256
    num_classes = None

    model = QPathformer(
        vocab_size=vocab_size,
        embed_dim=embed_dim,
        num_heads=num_heads,
        num_layers=num_layers,
        num_experts=num_experts,
        k=k,
        max_seq_len=max_seq_len,
        num_classes=num_classes,
    )

    dataset_size = 512
    seq_len = 128
    data = torch.randint(0, vocab_size, (dataset_size, seq_len))
    input_sequences = data[:, :-1]
    target_sequences = data[:, 1:]
    dataset = torch.utils.data.TensorDataset(input_sequences, target_sequences)
    loader = torch.utils.data.DataLoader(dataset, batch_size=8, shuffle=True)

    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    manifest = train_qpathformer(
        model,
        loader,
        optimizer,
        criterion,
        device,
        epochs=3,
        alpha_path=0.01,
        alpha_expert=0.01,
        run_id="trial1",
    )

    manifest["config"] = {
        "vocab_size": vocab_size,
        "embed_dim": embed_dim,
        "num_heads": num_heads,
        "num_layers": num_layers,
        "num_experts": num_experts,
        "k": k,
        "max_seq_len": max_seq_len,
        "batch_size": 8,
        "learning_rate": 1e-3,
        "alpha_path": 0.01,
        "alpha_expert": 0.01,
        "epochs": 3,
        "dataset_size": dataset_size,
        "seq_len": seq_len,
        "device": str(device),
    }

    save_manifest(manifest)
