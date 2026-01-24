# -*- coding: utf-8 -*-
"""
Loop de treinamento do classificador BERT.

Adaptado do projeto E:\Projetos\BERT para integração com o portal PGE.
"""

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split, Subset
from torch.optim import AdamW
from transformers import get_linear_schedule_with_warmup
from typing import Dict, List, Optional, Callable, Any, Tuple
from pathlib import Path
import numpy as np
import logging
from sklearn.utils.class_weight import compute_class_weight

from sistemas.bert_training.ml.classifier import BertClassifier
from sistemas.bert_training.ml.dataset import TextClassificationDataset

logger = logging.getLogger(__name__)


class Trainer:
    """
    Classe responsável pelo treinamento do modelo BERT.
    """

    def __init__(
        self,
        model: BertClassifier,
        train_dataset,
        val_dataset=None,
        device: str = 'cuda',
        batch_size: int = 16,
        learning_rate: float = 5e-5,
        epochs: int = 10,
        warmup_steps: int = 0,
        weight_decay: float = 0.01,
        use_class_weights: bool = True,
        gradient_accumulation_steps: int = 1,
        early_stopping_patience: int = 3,
        progress_callback: Optional[Callable] = None
    ):
        """
        Inicializa o trainer.

        Args:
            model: Modelo BERT para treinar
            train_dataset: Dataset de treinamento
            val_dataset: Dataset de validação (opcional)
            device: Dispositivo (cuda/cpu)
            batch_size: Tamanho do batch
            learning_rate: Taxa de aprendizado
            epochs: Número de épocas
            warmup_steps: Steps de warmup
            weight_decay: Weight decay para regularização
            use_class_weights: Usar pesos para classes desbalanceadas
            gradient_accumulation_steps: Steps para acumular gradientes
            early_stopping_patience: Épocas sem melhoria para parar
            progress_callback: Callback para reportar progresso
        """
        self.model = model.to(device)
        self.device = device
        self.epochs = epochs
        self.batch_size = batch_size
        self.gradient_accumulation_steps = gradient_accumulation_steps
        self.early_stopping_patience = early_stopping_patience
        self.progress_callback = progress_callback

        # DataLoaders
        self.train_loader = DataLoader(
            train_dataset,
            batch_size=batch_size,
            shuffle=True,
            num_workers=0,
            pin_memory=True if device == 'cuda' else False
        )

        self.val_loader = None
        if val_dataset:
            self.val_loader = DataLoader(
                val_dataset,
                batch_size=batch_size,
                shuffle=False,
                num_workers=0,
                pin_memory=True if device == 'cuda' else False
            )

        # Class weights para lidar com desbalanceamento
        self.class_weights = None
        if use_class_weights:
            labels_list = self._get_labels_from_dataset(train_dataset)

            if labels_list:
                labels_array = np.array(labels_list)
                unique_classes_in_data = np.unique(labels_array)

                # Usa todas as classes do modelo
                num_classes = model.num_labels
                all_classes = np.arange(num_classes)

                # Calcula pesos para classes presentes
                weights_for_present = compute_class_weight(
                    class_weight='balanced',
                    classes=unique_classes_in_data,
                    y=labels_array
                )

                # Classes ausentes recebem peso 1.0 (neutro)
                weights = np.ones(num_classes, dtype=np.float32)
                for i, cls in enumerate(unique_classes_in_data):
                    weights[cls] = weights_for_present[i]

                self.class_weights = torch.tensor(weights, dtype=torch.float32).to(device)
                logger.info(f"Class weights calculados para {num_classes} classes")

        # Loss function
        self.criterion = nn.CrossEntropyLoss(weight=self.class_weights)

        # Optimizer
        self.optimizer = AdamW(
            model.parameters(),
            lr=learning_rate,
            weight_decay=weight_decay
        )

        # Scheduler
        total_steps = len(self.train_loader) * epochs
        self.scheduler = get_linear_schedule_with_warmup(
            self.optimizer,
            num_warmup_steps=warmup_steps,
            num_training_steps=total_steps
        )

        # Histórico de treinamento
        self.history: List[Dict[str, Any]] = []
        self.best_val_accuracy = 0.0
        self.best_model_state = None

    @staticmethod
    def _get_labels_from_dataset(dataset) -> Optional[List[int]]:
        """Extrai lista de labels do dataset."""
        if hasattr(dataset, 'labels'):
            return dataset.labels
        elif hasattr(dataset, 'dataset') and hasattr(dataset.dataset, 'labels'):
            # É um Subset
            return [dataset.dataset.labels[i] for i in dataset.indices]
        return None

    def train_epoch(self, epoch: int) -> float:
        """
        Treina uma época.

        Returns:
            Loss médio da época
        """
        self.model.train()
        total_loss = 0.0
        num_batches = len(self.train_loader)

        self.optimizer.zero_grad()

        for batch_idx, batch in enumerate(self.train_loader):
            # Move dados para GPU
            input_ids = batch['input_ids'].to(self.device)
            attention_mask = batch['attention_mask'].to(self.device)
            labels = batch['labels'].to(self.device)

            token_type_ids = None
            if 'token_type_ids' in batch:
                token_type_ids = batch['token_type_ids'].to(self.device)

            # Forward
            logits = self.model(input_ids, attention_mask, token_type_ids)
            loss = self.criterion(logits, labels)

            # Gradient accumulation
            loss = loss / self.gradient_accumulation_steps
            loss.backward()

            if (batch_idx + 1) % self.gradient_accumulation_steps == 0:
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                self.optimizer.step()
                self.scheduler.step()
                self.optimizer.zero_grad()

            total_loss += loss.item() * self.gradient_accumulation_steps

            # Log a cada 10% do epoch
            if (batch_idx + 1) % max(1, num_batches // 10) == 0:
                logger.info(f"Epoch {epoch+1} - Batch {batch_idx+1}/{num_batches} - Loss: {loss.item():.4f}")

        avg_loss = total_loss / num_batches
        return avg_loss

    def validate(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Valida o modelo.

        Returns:
            Tuple de (loss, accuracy)
        """
        if not self.val_loader:
            return None, None

        self.model.eval()
        total_loss = 0.0
        correct = 0
        total = 0

        with torch.no_grad():
            for batch in self.val_loader:
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                labels = batch['labels'].to(self.device)

                token_type_ids = None
                if 'token_type_ids' in batch:
                    token_type_ids = batch['token_type_ids'].to(self.device)

                logits = self.model(input_ids, attention_mask, token_type_ids)
                loss = self.criterion(logits, labels)

                total_loss += loss.item()

                predictions = torch.argmax(logits, dim=-1)
                correct += (predictions == labels).sum().item()
                total += labels.size(0)

        avg_loss = total_loss / len(self.val_loader)
        accuracy = correct / total

        return avg_loss, accuracy

    def train(self) -> List[Dict[str, Any]]:
        """
        Executa o loop de treinamento completo.

        Returns:
            Histórico de treinamento
        """
        logger.info(f"Iniciando treinamento por {self.epochs} épocas")
        logger.info(f"Device: {self.device}")
        logger.info(f"Batch size: {self.batch_size}")

        epochs_without_improvement = 0

        for epoch in range(self.epochs):
            logger.info(f"\n{'='*50}")
            logger.info(f"Época {epoch + 1}/{self.epochs}")
            logger.info(f"{'='*50}")

            # Treinamento
            train_loss = self.train_epoch(epoch)

            # Validação
            val_loss, val_accuracy = self.validate()

            # Registra histórico
            epoch_data = {
                'epoch': epoch + 1,
                'train_loss': train_loss,
                'val_loss': val_loss,
                'val_accuracy': val_accuracy
            }
            self.history.append(epoch_data)

            # Log
            log_msg = f"Epoch {epoch + 1}: Train Loss = {train_loss:.4f}"
            if val_loss is not None:
                log_msg += f", Val Loss = {val_loss:.4f}, Val Acc = {val_accuracy:.4f}"
            logger.info(log_msg)

            # Callback de progresso
            if self.progress_callback:
                self.progress_callback(epoch_data)

            # Early stopping e salvamento do melhor modelo
            if val_accuracy is not None:
                if val_accuracy > self.best_val_accuracy:
                    self.best_val_accuracy = val_accuracy
                    self.best_model_state = {k: v.clone() for k, v in self.model.state_dict().items()}
                    epochs_without_improvement = 0
                    logger.info(f"Novo melhor modelo! Val Accuracy: {val_accuracy:.4f}")
                else:
                    epochs_without_improvement += 1

                if epochs_without_improvement >= self.early_stopping_patience:
                    logger.info(f"Early stopping após {epoch + 1} épocas")
                    break

        # Restaura o melhor modelo
        if self.best_model_state:
            self.model.load_state_dict(self.best_model_state)
            logger.info(f"Modelo restaurado para melhor checkpoint (Val Acc: {self.best_val_accuracy:.4f})")

        return self.history


def split_dataset(
    dataset,
    train_split: float = 0.7,
    seed: int = 42
) -> Tuple[Subset, Subset]:
    """
    Divide o dataset em treino e validação de forma determinística.

    Args:
        dataset: Dataset completo
        train_split: Proporção para treino
        seed: Seed para reprodutibilidade

    Returns:
        Tuple de (train_dataset, val_dataset)
    """
    train_size = int(len(dataset) * train_split)
    val_size = len(dataset) - train_size

    train_dataset, val_dataset = random_split(
        dataset,
        [train_size, val_size],
        generator=torch.Generator().manual_seed(seed)
    )

    logger.info(f"Dataset dividido: {train_size} treino, {val_size} validação (seed={seed})")

    return train_dataset, val_dataset
