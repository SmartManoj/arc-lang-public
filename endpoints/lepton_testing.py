import time
import asyncio

from openai import AsyncOpenAI
from devtools import debug
from pydantic import BaseModel
import os

vllm = AsyncOpenAI(
    base_url=os.environ["VLLM_ENDPOINT"], api_key=os.environ["VLLM_API_KEY"]
)
sglang = AsyncOpenAI(
    base_url=os.environ["SGLANG_ENDPOINT"], api_key=os.environ["SGLANG_API_KEY"]
)

vllm_model_name = "openai/gpt-oss-120b"
sglang_model_name = "lmsys/gpt-oss-120b-bf16"


class InstructionsResult(BaseModel):
    instructions: str


class ReasoningResponse(BaseModel):
    reasoning: str
    result: str


async def run() -> ReasoningResponse:
    messages = [
        {"role": "system", "content": "Talk like a pirate."},
        {"role": "user", "content": "what is 993 * 298?"},
    ]
    # result = await vllm.responses.create(
    #     model=vllm_model_name,
    #     input=messages,
    # )
    # result = await vllm.chat.completions.create(
    #     model=vllm_model_name,
    #     messages=messages,
    # )
    result = await vllm.responses.parse(
        model=vllm_model_name,
        input=messages,
        # text_format=InstructionsResult,
        max_output_tokens=128_000,
        reasoning={"effort": "high"},
    )
    # debug(result)
    reasoning_text = ""
    response_text = ""
    for output in result.output:
        if output.type == "reasoning":
            reasoning_text = "\n".join([c["text"] for c in output.content])
        if output.type == "message":
            response_text = "\n".join([c.text for c in output.content])

    return ReasoningResponse(reasoning=reasoning_text, result=response_text)


async def main() -> None:
    start = time.time()
    futures = [run() for _ in range(20)]
    runs = await asyncio.gather(*futures)
    took = time.time() - start
    debug(runs)
    print("took", took)


if __name__ == "__main__":
    asyncio.run(main())
