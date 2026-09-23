import argparse

from nanovllm import LLM, SamplingParams


def parse_args():
    parser = argparse.ArgumentParser(description="Run Nano-vLLM on Cambricon MLU")
    parser.add_argument("model", help="Local Hugging Face Qwen3 model directory")
    parser.add_argument("--tp", type=int, default=1, help="Tensor parallel size")
    parser.add_argument(
        "--use-graph",
        action="store_true",
        help="Enable MLU Graph after eager-mode validation",
    )
    parser.add_argument("--max-tokens", type=int, default=64)
    return parser.parse_args()


def main():
    args = parse_args()
    llm = LLM(
        args.model,
        device="mlu",
        enforce_eager=not args.use_graph,
        tensor_parallel_size=args.tp,
    )
    outputs = llm.generate(
        ["请简要介绍寒武纪 MLU。"],
        SamplingParams(temperature=0.6, max_tokens=args.max_tokens),
    )
    print(outputs[0]["text"])


if __name__ == "__main__":
    main()
