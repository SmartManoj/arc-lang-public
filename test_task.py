import asyncio
from pathlib import Path
from src.run import run_from_json, evaluate_solutions
from src.configs.local_test_config import local_test_config

async def main():
    year = "2025"
    train_or_eval = "evaluation"
    root_dir = Path(__file__).parent

    challenges_path = (
        root_dir
        / "data"
        / f"arc-prize-{year}"
        / f"arc-agi_{train_or_eval}_challenges.json"
    )

    solutions_path = (
        root_dir
        / "data"
        / f"arc-prize-{year}"
        / f"arc-agi_{train_or_eval}_solutions.json"
    )

    attempts_path = (
        root_dir
        / "attempts"
        / f"arc-prize-{year}"
        / f"arc-agi_{train_or_eval}_attempts.json"
    )

    temp_attempts_path = root_dir / "attempts" / f"arc-prize-{year}" / "temp_solutions"

    print(f"Testing task 7b5033c1 from {train_or_eval} set...")
    
    await run_from_json(
        challenges_path=challenges_path,
        truth_solutions_path=solutions_path,
        config=local_test_config,
        attempts_path=attempts_path,
        temp_attempts_dir=temp_attempts_path,
        limit=None,
        offset=0,
        task_ids={"7b5033c1"},
    )

    print("\nEvaluating results...")
    if attempts_path.exists():
        evaluate_solutions(
            attempts_solutions_path=attempts_path, 
            truth_solutions_path=solutions_path
        )
    else:
        print(f"Attempts file not found at {attempts_path}")

if __name__ == "__main__":
    asyncio.run(main())
    from pymsgbox import alert
    alert("Test complete")

