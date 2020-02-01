import argparse
from pprint import pprint

from metaworld.benchmarks import ML1

from ppo import PPOPolicy
from storage import RolloutStorage


def main(args: argparse.Namespace):
    """ Main function for main.py. """

    # Get environment and set task.
    env_name = args.env_name
    env = ML1.get_train_tasks(env_name)
    tasks = env.sample_tasks(1)
    env.set_task(tasks[0])

    # Create policy and rollout storage.
    policy = PPOPolicy(observation_space=env.observation_space, action_space=env.action_space)
    rollouts = RolloutStorage()

    # Initialize environment and set first observation.
    obs = env.reset()
    rollouts.set_initial_obs(obs)

    # Training loop.
    for iteration in range(args.num_iterations):

        # Rollout loop.
        for t in range(args.rollout_length):

            # Sample actions.
            value, action = policy.act(rollouts.obs[t])

            # Perform step and record in ``rollouts``.
            obs, reward, done, info = env.step(action)
            rollouts.add_step(obs, action, value, reward)

        # Compute update.
        policy.update(rollouts)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--num_iterations",
        type=int,
        default=100,
        help="Number of PPO training iterations (outer loop).",
    )
    parser.add_argument(
        "--rollout_length",
        type=int,
        default=100,
        help="Length of rollout (inner loop).",
    )
    parser.add_argument(
        "--env-name",
        type=str,
        default="bin-picking-v1",
        help="Which Meta-World environment to run.",
    )
    args = parser.parse_args()

    main(args)
