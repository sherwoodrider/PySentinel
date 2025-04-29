from sentence_transformers import SentenceTransformer
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
model_name = 'paraphrase-multilingual-MiniLM-L12-v2'
local_model_path = os.path.join('D:\hugging_face\models',model_name)
print(local_model_path)
os.makedirs(local_model_path, exist_ok=True)

print("download model begin")
model = SentenceTransformer(model_name)
model.save(local_model_path)
print(f"download model save to : {local_model_path}")