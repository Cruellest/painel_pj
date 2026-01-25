# -*- coding: utf-8 -*-
"""
Testes para o módulo BERT Training.

Testes unitários e de integração que não requerem GPU real.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd


def _can_import_torch() -> bool:
    """Verifica se PyTorch está disponível."""
    try:
        import torch
        return True
    except ImportError:
        return False


# ==================== Testes de Validação de Excel ====================

class TestExcelValidation:
    """Testes de validação de arquivos Excel."""

    def test_validate_text_classification_valid(self, tmp_path):
        """Testa validação de Excel válido para classificação de texto."""
        from sistemas.bert_training.services import validate_excel_file
        from sistemas.bert_training.schemas import TaskTypeEnum

        # Cria Excel de teste
        df = pd.DataFrame({
            'texto': ['texto1', 'texto2', 'texto3', 'texto4', 'texto5'] * 20,
            'label': ['A', 'B', 'A', 'B', 'A'] * 20
        })
        excel_path = tmp_path / "test_dataset.xlsx"
        df.to_excel(excel_path, index=False)

        result = validate_excel_file(
            file_path=excel_path,
            task_type=TaskTypeEnum.TEXT_CLASSIFICATION,
            text_column='texto',
            label_column='label'
        )

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.total_rows == 100
        assert 'texto' in result.columns
        assert 'label' in result.columns

    def test_validate_missing_column(self, tmp_path):
        """Testa validação com coluna faltante."""
        from sistemas.bert_training.services import validate_excel_file
        from sistemas.bert_training.schemas import TaskTypeEnum

        df = pd.DataFrame({'texto': ['a', 'b', 'c'] * 40})
        excel_path = tmp_path / "test_missing_col.xlsx"
        df.to_excel(excel_path, index=False)

        result = validate_excel_file(
            file_path=excel_path,
            task_type=TaskTypeEnum.TEXT_CLASSIFICATION,
            text_column='texto',
            label_column='label_inexistente'
        )

        assert result.is_valid is False
        assert any('label_inexistente' in err for err in result.errors)

    def test_validate_insufficient_labels(self, tmp_path):
        """Testa validação com menos de 2 labels."""
        from sistemas.bert_training.services import validate_excel_file
        from sistemas.bert_training.schemas import TaskTypeEnum

        df = pd.DataFrame({
            'texto': ['a', 'b', 'c'] * 40,
            'label': ['A', 'A', 'A'] * 40  # Apenas uma label
        })
        excel_path = tmp_path / "test_one_label.xlsx"
        df.to_excel(excel_path, index=False)

        result = validate_excel_file(
            file_path=excel_path,
            task_type=TaskTypeEnum.TEXT_CLASSIFICATION,
            text_column='texto',
            label_column='label'
        )

        assert result.is_valid is False
        assert any('2 labels' in err for err in result.errors)

    def test_validate_token_classification_valid(self, tmp_path):
        """Testa validação de Excel válido para classificação de tokens (NER)."""
        from sistemas.bert_training.services import validate_excel_file
        from sistemas.bert_training.schemas import TaskTypeEnum

        df = pd.DataFrame({
            'tokens': [
                json.dumps(['O', 'João', 'mora', 'em', 'SP']),
                json.dumps(['Maria', 'trabalha', 'no', 'RJ']),
            ] * 60,
            'tags': [
                json.dumps(['O', 'B-PER', 'O', 'O', 'B-LOC']),
                json.dumps(['B-PER', 'O', 'O', 'B-LOC']),
            ] * 60
        })
        excel_path = tmp_path / "test_ner.xlsx"
        df.to_excel(excel_path, index=False)

        result = validate_excel_file(
            file_path=excel_path,
            task_type=TaskTypeEnum.TOKEN_CLASSIFICATION,
            text_column='tokens',
            label_column='tags'
        )

        assert result.is_valid is True
        assert result.total_rows == 120


# ==================== Testes de Hash ====================

class TestSHA256:
    """Testes de cálculo de hash SHA256."""

    def test_calculate_sha256(self, tmp_path):
        """Testa cálculo de hash SHA256."""
        from sistemas.bert_training.services import calculate_sha256

        # Cria arquivo de teste
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("conteudo de teste")

        hash_result = calculate_sha256(test_file)

        assert len(hash_result) == 64  # SHA256 tem 64 caracteres hex
        assert hash_result.isalnum()

    def test_same_content_same_hash(self, tmp_path):
        """Testa que mesmo conteúdo gera mesmo hash."""
        from sistemas.bert_training.services import calculate_sha256

        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        content = "conteudo identico"
        file1.write_text(content)
        file2.write_text(content)

        assert calculate_sha256(file1) == calculate_sha256(file2)

    def test_different_content_different_hash(self, tmp_path):
        """Testa que conteúdos diferentes geram hashes diferentes."""
        from sistemas.bert_training.services import calculate_sha256

        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("conteudo A")
        file2.write_text("conteudo B")

        assert calculate_sha256(file1) != calculate_sha256(file2)


# ==================== Testes de Schemas ====================

class TestSchemas:
    """Testes dos schemas Pydantic."""

    def test_hyperparameters_defaults(self):
        """Testa valores padrão de hiperparâmetros."""
        from sistemas.bert_training.schemas import HyperparametersConfig

        config = HyperparametersConfig()

        assert config.learning_rate == 5e-5
        assert config.batch_size == 16
        assert config.epochs == 10
        assert config.max_length == 512
        assert config.train_split == 0.7
        assert config.seed == 42

    def test_hyperparameters_validation(self):
        """Testa validação de hiperparâmetros inválidos."""
        from sistemas.bert_training.schemas import HyperparametersConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            HyperparametersConfig(learning_rate=-1)  # Deve ser positivo

        with pytest.raises(ValidationError):
            HyperparametersConfig(train_split=1.5)  # Deve ser < 1.0

    def test_run_create_schema(self):
        """Testa schema de criação de run."""
        from sistemas.bert_training.schemas import RunCreate

        run = RunCreate(
            name="Test Run",
            dataset_id=1,
            base_model="neuralmind/bert-base-portuguese-cased"
        )

        assert run.name == "Test Run"
        assert run.dataset_id == 1
        assert run.hyperparameters.epochs == 10  # Valor padrão

    def test_metric_create_schema(self):
        """Testa schema de criação de métrica."""
        from sistemas.bert_training.schemas import MetricCreate

        metric = MetricCreate(
            worker_token="test_token",
            run_id=1,
            epoch=1,
            train_loss=0.5,
            val_accuracy=0.85
        )

        assert metric.epoch == 1
        assert metric.train_loss == 0.5
        assert metric.val_accuracy == 0.85


# ==================== Testes de Dataset ML ====================

class TestMLDataset:
    """Testes do dataset PyTorch (sem GPU)."""

    def test_create_label_encoder(self):
        """Testa criação de encoder de labels."""
        from sistemas.bert_training.ml.dataset import create_label_encoder

        labels = ['B', 'A', 'C', 'A', 'B']
        label_to_id, id_to_label = create_label_encoder(labels)

        assert len(label_to_id) == 3
        assert label_to_id['A'] == 0  # Ordenado alfabeticamente
        assert label_to_id['B'] == 1
        assert label_to_id['C'] == 2
        assert id_to_label[0] == 'A'
        assert id_to_label[1] == 'B'
        assert id_to_label[2] == 'C'

    @pytest.mark.skipif(
        not _can_import_torch(),
        reason="PyTorch não disponível"
    )
    def test_text_classification_dataset(self):
        """Testa criação de dataset de classificação de texto."""
        from sistemas.bert_training.ml.dataset import TextClassificationDataset

        texts = ['texto um', 'texto dois', 'texto tres']
        labels = [0, 1, 0]

        dataset = TextClassificationDataset(
            texts=texts,
            labels=labels,
            tokenizer_name='bert-base-multilingual-cased',  # Modelo menor para teste
            max_length=32
        )

        assert len(dataset) == 3
        item = dataset[0]
        assert 'input_ids' in item
        assert 'attention_mask' in item
        assert 'labels' in item


# ==================== Testes de Worker (Mock) ====================

class TestWorkerMock:
    """Testes do worker com mocks (sem GPU real)."""

    def test_worker_check_gpu_unavailable(self):
        """Testa detecção de GPU indisponível."""
        with patch('torch.cuda.is_available', return_value=False):
            from sistemas.bert_training.ml.classifier import verify_gpu_available

            result = verify_gpu_available()

            assert result['available'] is False
            assert 'error' in result

    def test_worker_dry_run_mode(self):
        """Testa modo dry-run do worker."""
        # Testa que a classe pode ser instanciada em dry-run
        from sistemas.bert_training.worker.bert_worker import BertWorker

        worker = BertWorker(
            api_url="http://localhost:8000",
            token="test_token",
            dry_run=True
        )

        assert worker.dry_run is True
        assert worker.api_url == "http://localhost:8000"


# ==================== Testes de Extração de Metadados ====================

class TestMetadataExtraction:
    """Testes de extração de metadados de dataset."""

    def test_extract_dataset_metadata(self, tmp_path):
        """Testa extração de metadados de dataset."""
        from sistemas.bert_training.services import extract_dataset_metadata
        from sistemas.bert_training.schemas import TaskTypeEnum

        df = pd.DataFrame({
            'texto': ['texto A', 'texto B', 'texto C', 'texto D'] * 25,
            'classe': ['X', 'Y', 'X', 'Z'] * 25
        })
        excel_path = tmp_path / "test_metadata.xlsx"
        df.to_excel(excel_path, index=False)

        metadata = extract_dataset_metadata(
            file_path=excel_path,
            task_type=TaskTypeEnum.TEXT_CLASSIFICATION,
            text_column='texto',
            label_column='classe'
        )

        assert metadata['total_rows'] == 100
        assert metadata['total_labels'] == 3
        assert 'X' in metadata['label_distribution']
        assert 'Y' in metadata['label_distribution']
        assert 'Z' in metadata['label_distribution']
        assert len(metadata['sample_preview']) <= 10


# ==================== Helpers ====================

def _can_import_torch():
    """Verifica se PyTorch pode ser importado."""
    try:
        import torch
        return True
    except ImportError:
        return False


# ==================== Fixtures ====================

@pytest.fixture
def tmp_path(tmp_path_factory):
    """Cria diretório temporário para testes."""
    return tmp_path_factory.mktemp("bert_training_tests")
