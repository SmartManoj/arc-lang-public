from src.configs.models import Model, RunConfig, Step, StepRevision, StepRevisionPool

instruction_model = Model.sglang_gpt_oss_120b
grid_model = Model.sglang_gpt_oss_120b

oss_120b_prod = RunConfig(
    final_follow_model=grid_model,
    final_follow_times=5,
    max_concurrent_tasks=120,
    steps=[
        # Step(
        #     instruction_model=instruction_model,
        #     follow_model=grid_model,
        #     times=5,
        #     timeout_secs=300,
        #     include_base64=False,
        #     use_diffs=True,
        # ),
        # Step(
        #     instruction_model=instruction_model,
        #     follow_model=grid_model,
        #     times=25,
        #     timeout_secs=300,
        #     include_base64=False,
        #     use_diffs=True,
        # ),
        Step(
            instruction_model=instruction_model,
            follow_model=grid_model,
            times=50,
            timeout_secs=300,
            include_base64=False,
            use_diffs=True,
        ),
        # StepRevision(
        #     top_scores_used=5,
        #     instruction_model=model,
        #     follow_model=model,
        #     times_per_top_score=1,
        #     timeout_secs=300,
        #     include_base64=False,
        #     use_diffs=True,
        # ),
        # StepRevisionPool(
        #     top_scores_used=5,
        #     instruction_model=instruction_model,
        #     follow_model=grid_model,
        #     times=5,
        #     timeout_secs=300,
        #     include_base64=False,
        #     use_diffs=True,
        # ),
    ],
)
