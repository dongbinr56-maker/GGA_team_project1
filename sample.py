import streamlit as st
from transformers import AutoProcessor, Gemma3nForConditionalGeneration
import torch
from PIL import Image

st.title("Gemma VLM: 이미지 스토리 생성")

# -------------------- 디바이스 & dtype 설정 --------------------
if torch.backends.mps.is_available():
    device = "mps"   # 맥북(M1/M2 등) GPU
elif torch.cuda.is_available():
    device = "cuda"  # NVIDIA Tesla 등
else:
    device = "cpu"

dtype = torch.float16 if device == "cuda" else torch.float32

# -------------------- 모델 로드 --------------------
model_id = "google/gemma-3n-e2b-it"  # VLM 모델
@st.cache_resource
def load_model():
    model = Gemma3nForConditionalGeneration.from_pretrained(
        model_id, torch_dtype=dtype
    ).eval().to(device)
    processor = AutoProcessor.from_pretrained(model_id)
    return model, processor

model, processor = load_model()

# -------------------- UI --------------------
uploaded_file = st.file_uploader("이미지를 업로드하세요", type=["jpg","jpeg","png"])
user_caption = st.text_input("간단한 설명을 입력하세요:")

if st.button("스토리 생성하기"):
    if uploaded_file is None:
        st.warning("이미지를 업로드해주세요.")
    else:
        image = Image.open(uploaded_file).convert("RGB")

        messages = [
            {"role":"system","content":[{"type":"text","text":"You are a helpful assistant that writes stories about images."}]},
            {"role":"user","content":[
                {"type":"image","image": image},
                {"type":"text","text": f"간단 설명: {user_caption}\n이 이미지에 대한 짧은 스토리를 만들어줘."}
            ]}
        ]

        # 프롬프트 생성
        prompt = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)

        # 입력 변환 (이미지+텍스트)
        inputs = processor(images=image, text=prompt, return_tensors="pt", padding=True).to(device)

        # 모델 추론
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=200, do_sample=True)

        result = processor.decode(out[0], skip_special_tokens=True)

        # 결과 출력
        st.subheader("생성된 스토리")
        st.write(result)
