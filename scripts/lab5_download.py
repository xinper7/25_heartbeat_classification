"""Download public model weights; no business data is uploaded."""
from pathlib import Path
from huggingface_hub import snapshot_download
ROOT=Path(__file__).resolve().parents[1]
snapshot_download('Qwen/Qwen2.5-0.5B-Instruct',local_dir=ROOT/'runtime/agent/base',allow_patterns=['*.json','*.safetensors','*.txt','*.model','LICENSE'])
