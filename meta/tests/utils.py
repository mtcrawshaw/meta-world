""" Utilities for meta/tests. """

from typing import Dict, Any

import torch
from gym import Env

from meta.ppo import PPOPolicy
from meta.storage import RolloutStorage

DEFAULT_SETTINGS = {
    "env_name": "CartPole-v1",
    "rollout_length": 32,
    "num_ppo_epochs": 1,
    "lr": 3e-4,
    "eps": 1e-5,
    "value_loss_coeff": 0.5,
    "entropy_loss_coeff": 0.01,
    "gamma": 0.99,
    "gae_lambda": 0.95,
    "num_minibatch": 1,
    "clip_param": 0.2,
    "max_grad_norm": 0.5,
    "clip_value_loss": False,
    "num_layers": 3,
    "hidden_size": 64,
    "normalize_advantages": True,
    "seed": 1,
    "num_episodes": 4,
    "episode_len": 8,
    "num_processes": 1,
    "device": torch.device("cpu"),
}


def get_policy(env: Env, settings: Dict[str, Any]) -> PPOPolicy:
    """ Return a PPOPolicy for ``env`` for use in test cases. """

    policy = PPOPolicy(
        observation_space=env.observation_space,
        action_space=env.action_space,
        num_ppo_epochs=settings["num_ppo_epochs"],
        lr=settings["lr"],
        eps=settings["eps"],
        value_loss_coeff=settings["value_loss_coeff"],
        entropy_loss_coeff=settings["entropy_loss_coeff"],
        gamma=settings["gamma"],
        gae_lambda=settings["gae_lambda"],
        num_minibatch=settings["num_minibatch"],
        clip_param=settings["clip_param"],
        max_grad_norm=settings["max_grad_norm"],
        clip_value_loss=settings["clip_value_loss"],
        num_layers=settings["num_layers"],
        hidden_size=settings["hidden_size"],
        normalize_advantages=settings["normalize_advantages"],
        device=settings["device"],
    )
    return policy


def get_rollout(
    env: Env,
    policy: PPOPolicy,
    num_episodes: int,
    episode_len: int,
    num_processes: int,
    device: torch.device,
) -> RolloutStorage:
    """
    Collects ``num_episodes`` episodes of size ``episode_len`` from ``env`` using
    ``policy``. Note that we explicitly call env.reset() here assuming that the
    environment will never return done=True, so this function should not be used with an
    environment which may return done=True.
    """

    rollout_len = num_episodes * episode_len
    rollout = RolloutStorage(
        rollout_length=rollout_len,
        observation_space=env.observation_space,
        action_space=env.action_space,
        num_processes=num_processes,
        hidden_state_size=1,
        device=device,
    )
    rollout.set_initial_obs(env.reset())

    # Generate rollout.
    hidden_state = torch.zeros(1)
    for _ in range(num_episodes):

        for rollout_step in range(episode_len):
            with torch.no_grad():
                value_pred, action, action_log_prob, hidden_state = policy.act(
                    rollout.obs[rollout_step], hidden_state, None
                )
            obs, reward, done, _ = env.step(action)

            # Putting this here so that obs and done get set before adding to rollout.
            if rollout_step == episode_len - 1:
                obs = env.reset()
                done = [True]

            rollout.add_step(obs, action, done, action_log_prob, value_pred, reward, hidden_state)

    return rollout
