import os
os.environ.pop("HF_HUB_OFFLINE", None)
os.environ.pop("TRANSFORMERS_OFFLINE", None)

import traceback
from huggingface_hub import hf_hub_download

# Try with longer timeout
try:
    p = hf_hub_download(
        repo_id="miracl/miracl",
        filename="miracl-v1.0-zh/topics/topics.miracl-v1.0-zh-dev.tsv",
        repo_type="dataset",
        etag_timeout=60,
    )
    print("OK:", p)
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:300])

# Try listing files in the repo
try:
    from huggingface_hub import list_repo_files
    files = list_repo_files("miracl/miracl", repo_type="dataset")
    zh_files = [f for f in files if "zh" in f.lower()]
    print(f"Total files: {len(files)}, zh files: {len(zh_files)}")
    for f in zh_files[:20]:
        print(f"  {f}")
except Exception as e:
    print("LIST FAIL:", type(e).__name__, str(e)[:300])
