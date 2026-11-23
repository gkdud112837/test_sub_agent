import os

from dotenv import load_dotenv
from google import genai

load_dotenv()  # .env 파일을 환경변수로 읽어옴

MODEL_NAME = os.environ["MODEL_NAME"]  # 사용할 Gemini 모델 이름
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])  # .env의 키로 클라이언트 생성


if __name__ == "__main__":
    # 1단계 확인용: 단순 호출 1회
    interaction = client.interactions.create(model=MODEL_NAME, input="안녕")
    print(interaction.output_text)
