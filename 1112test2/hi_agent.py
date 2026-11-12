"""터미널 대화 챗봇 — Claude Code 구독(로그인 계정)으로 동작.

준비:
    pip install claude-agent-sdk
    (Claude Code 에 구독 계정으로 로그인되어 있어야 함. ANTHROPIC_API_KEY 는 비워 둘 것)

실행:
    python hi_agent.py      # 'quit' 입력 시 종료
"""

import asyncio

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

MODEL = "claude-sonnet-5-5"

SYSTEM_PROMPT = (
    "너는 사용자의 다정한 대화 챗봇이야. "
    "첫 인사는 '안녕! 나는 너의 대화 챗봇이야. 오늘 무슨 이야기 나눠 볼까?'처럼 "
    "친절하고 밝게 해 줘. 항상 한국어로, 짧고 따뜻하게 대답해."
)

# 대화 기록: {"role": "user" | "assistant", "content": str}
history: list[dict[str, str]] = []


def build_prompt() -> str:
    """지금까지의 대화 기록을 하나의 프롬프트로 묶는다."""
    lines = []
    for msg in history:
        speaker = "사용자" if msg["role"] == "user" else "챗봇"
        lines.append(f"{speaker}: {msg['content']}")
    lines.append("챗봇:")
    return "\n".join(lines)


async def ask_claude() -> str:
    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        tools=[],      # 파일·명령 도구 없이 대화만
        max_turns=1,
    )
    reply = []
    async for message in query(prompt=build_prompt(), options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    reply.append(block.text)
    return "".join(reply).strip()


async def main() -> None:
    # 첫 인사
    history.append({"role": "user", "content": "(대화 시작) 나에게 인사해 줘."})
    greeting = await ask_claude()
    history.append({"role": "assistant", "content": greeting})
    print(f"챗봇: {greeting}\n(끝내려면 quit 입력)\n")

    while True:
        user_input = input("나: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("챗봇: 이야기 나눠 줘서 고마워! 또 만나 👋")
            break

        history.append({"role": "user", "content": user_input})
        answer = await ask_claude()
        history.append({"role": "assistant", "content": answer})
        print(f"챗봇: {answer}\n")


if __name__ == "__main__":
    asyncio.run(main())
