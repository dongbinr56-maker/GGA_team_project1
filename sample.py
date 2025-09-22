# ------------------------------------------------------------
# Gemma 3n VLM + Streamlit: "이미지에 대해 모델이 어떻게 생각하는지" 한글 출력
# 요구 라이브러리(권장):
#   pip install -U transformers timm torch torchvision pillow streamlit
#   ※ Gemma3n 클래스는 최신 Transformers가 필요합니다 (v4.56+ 권장).
# ------------------------------------------------------------

import streamlit as st

# Hugging Face Transformers: 멀티모달(이미지+텍스트) 입출력용 프로세서/모델
from transformers import AutoProcessor, Gemma3nForConditionalGeneration
import torch
from PIL import Image, ImageOps


# -------------------- 앱 타이틀 --------------------
st.title("Gemma 3n VLM: 이미지에 대한 모델의 생각")

# -------------------- 디바이스 & dtype 설정 --------------------
# - CUDA(엔비디아) -> bfloat16 권장
# - Apple Silicon(MPS) -> float16 권장
# - CPU -> float32 (느리지만 동작은 함)
if torch.cuda.is_available():
    device = "cuda"
    dtype = torch.bfloat16
elif torch.backends.mps.is_available():
    device = "mps"
    dtype = torch.float16
else:
    device = "cpu"
    dtype = torch.float32

st.caption(f"Device: {device}, dtype: {dtype}")


# -------------------- 모델/프로세서 로드 --------------------
# 모델 체크포인트:
#  - 작은 모델:  google/gemma-3n-E2B-it  (빠름, 메모리 적음)
#  - 좀 더 큰 모델: google/gemma-3n-E4B-it (느리지만 품질↑)
MODEL_ID = "google/gemma-3n-E2B-it"  # 허깅페이스 모델 카드 표기와 대소문자 일치

@st.cache_resource(show_spinner=True)
def load_model_and_processor(model_id: str):
    """
    - 모델과 프로세서를 한 번만 초기화해서 캐시.
    - Gemma3nForConditionalGeneration: 멀티모달 입력을 받아 텍스트를 생성하는 VLM 헤드.
    - AutoProcessor: 이미지 전처리 + 토크나이저를 합친 일체형 프로세서.
    """
    model = Gemma3nForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype=dtype,
    ).to(device).eval()

    processor = AutoProcessor.from_pretrained(model_id)
    return model, processor

model, processor = load_model_and_processor(MODEL_ID)


# -------------------- 간단 UI --------------------
uploaded = st.file_uploader("이미지를 업로드하세요", type=["jpg", "jpeg", "png"])
user_hint = st.text_input("모델에게 줄 힌트(선택):", placeholder="예: 가족사진, 1990년대 감성, 바닷가…")

go = st.button("모델 생각 듣기")  # 최소한의 버튼


# -------------------- 추론 --------------------
if go:
    if uploaded is None:
        st.warning("이미지를 먼저 업로드해주세요.")
    else:
        # PIL 이미지 열기
        # - exif_orientation을 반영해서 올바른 방향으로 뒤집는 처리를 해줌
        image = Image.open(uploaded).convert("RGB")
        image = ImageOps.exif_transpose(image)

        st.image(image, caption="입력 이미지", use_container_width=True)

        # Gemma3n은 텍스트 안에 `<image_soft_token>` 토큰 위치에 이미지를 매핑함.
        # (여러 장도 가능하지만, 여기선 1장만)
        # 힌트가 있으면 추가로 컨텍스트를 제공.
        prompt_text = (
            "<image_soft_token> "
            "위 사진을 보고 느낀 점을 2~3문장으로 '한국어'로 간결하게 말해줘. "
            "과장 없이 사실 위주로. "
        )
        if user_hint.strip():
            prompt_text += f"(참고 힌트: {user_hint.strip()})"

        # Processor가 이미지 전처리(리사이즈/정규화 등)와 텍스트 토크나이징을 한 번에 수행
        # - images: [PIL.Image] 리스트(batch 형태 요구)
        # - text: 위에서 만든 prompt_text (image_soft_token 포함)
        inputs = processor(
            images=[image],
            text=prompt_text,
            return_tensors="pt",
            padding=True,
        ).to(device)

        # 생성
        gen_kwargs = dict(
            max_new_tokens=160,   # 생성 토큰 길이
            do_sample=False,      # 깔끔한 요약 느낌(샘플링 비활성). 다양성 원하면 True + temperature 조정
            # temperature=0.7,    # do_sample=True일 때만 유효
        )

        with st.spinner("모델이 이미지를 해석하는 중…"):
            with torch.inference_mode():
                outputs = model.generate(**inputs, **gen_kwargs)

        # 디코딩: 특수토큰 제거
        text = processor.decode(outputs[0], skip_special_tokens=True)

        # 결과에서 프롬프트/대화 앞부분을 출력하는 모델이 있을 수 있어,
        # 실제 답변만 보이도록 후처리(가벼운 절단) — 너무 공격적으로 자르지는 않음.
        # 가장 마지막 문장 덩어리만 쓰고 싶다면 아래를 더 강하게 커스텀 가능.
        st.subheader("모델의 한 줄 생각")
        st.write(text.strip())
