from math import exp, log
from typing import Dict, Any

import torch
import numpy as np
import gym

from meta.ppo import PPOPolicy
from meta.storage import RolloutStorage
from meta.utils import get_env
from meta.tests.utils import get_policy, DEFAULT_SETTINGS
from meta.tests.envs import UniquePolicy


TOL = 1e-5


def test_act_sizes():
    """ Test the sizes of returned tensors from ppo.act(). """

    settings = dict(DEFAULT_SETTINGS)
    env = get_env(settings["env_name"])
    policy = get_policy(env, settings)
    obs = env.observation_space.sample()

    value_pred, action, action_log_prob = policy.act(obs)

    assert isinstance(value_pred, torch.Tensor)
    assert value_pred.shape == torch.Size([1])
    assert isinstance(action, torch.Tensor)
    assert action.shape == torch.Size(env.action_space.shape)
    assert isinstance(action_log_prob, torch.Tensor)
    assert action_log_prob.shape == torch.Size([1])


def test_act_values():
    """ Test the values in the returned tensors from ppo.act(). """

    settings = dict(DEFAULT_SETTINGS)
    env = get_env("unique-env")
    policy = UniquePolicy()
    obs = env.observation_space.sample()

    value_pred, action, action_log_prob = policy.act(obs)

    assert isinstance(value_pred, torch.Tensor)
    assert float(value_pred) == obs
    assert isinstance(action, torch.Tensor)
    assert float(action) - int(action) == 0.0 and int(action) in env.action_space
    env = get_env("unique-env")
    policy = UniquePolicy()
    obs = env.observation_space.sample()

    value_pred, action, action_log_prob = policy.act(obs)

    assert isinstance(value_pred, torch.Tensor)
    assert float(value_pred) == obs
    assert isinstance(action, torch.Tensor)
    assert float(action) - int(action) == 0.0 and int(action) in env.action_space
    assert isinstance(action_log_prob, torch.Tensor)
    assert (
        abs(
            float(action_log_prob)
            - log(float(policy.policy_network.action_probs(obs)[int(action)]))
        )
        < TOL
    )


def test_evaluate_actions_sizes():
    """ Test the sizes of returned tensors from ppo.evaluate_actions(). """

    settings = dict(DEFAULT_SETTINGS)
    env = get_env(settings["env_name"])
    policy = get_policy(env, settings)
    obs_list = [
        torch.Tensor(env.observation_space.sample())
        for _ in range(settings["minibatch_size"])
    ]
    obs_batch = torch.stack(obs_list)
    actions_list = [
        torch.Tensor([float(env.action_space.sample())])
        for _ in range(settings["minibatch_size"])
    ]
    actions_batch = torch.stack(actions_list)

    value_pred, action_log_prob, action_dist_entropy = policy.evaluate_actions(
        obs_batch, actions_batch
    )

    assert isinstance(value_pred, torch.Tensor)
    assert value_pred.shape == torch.Size([settings["minibatch_size"]])
    assert isinstance(action_log_prob, torch.Tensor)
    assert action_log_prob.shape == torch.Size([settings["minibatch_size"]])
    assert isinstance(action_log_prob, torch.Tensor)
    assert action_dist_entropy.shape == torch.Size([settings["minibatch_size"]])


def evaluate_actions_values():
    """ Test the values in the returned tensors from ppo.evaluate_actions(). """
    raise NotImplementedError


def test_get_value_sizes():
    """ Test the sizes of returned tensors from ppo.get_value(). """

    settings = dict(DEFAULT_SETTINGS)
    env = get_env(settings["env_name"])
    policy = get_policy(env, settings)
    obs = env.observation_space.sample()

    value_pred = policy.get_value(obs)

    assert isinstance(value_pred, torch.Tensor)
    assert value_pred.shape == torch.Size([1])


def get_value_values():
    """ Test the values of returned tensors from ppo.get_value(). """
    raise NotImplementedError


def test_update_values():
    """
    Tests whether PPOPolicy.update() calculates correct loss values.
    """

    # Initialize environment and policy.
    settings = dict(DEFAULT_SETTINGS)
    settings["env_name"] = "parity-env"
    env = get_env(settings["env_name"])
    policy = get_policy(env, settings)

    # Generate rollout.
    rollouts = RolloutStorage(
        rollout_length=settings["rollout_length"],
        observation_space=env.observation_space,
        action_space=env.action_space,
    )
    obs = env.reset()
    rollouts.set_initial_obs(obs)
    for rollout_step in range(settings["rollout_length"]):
        with torch.no_grad():
            value_pred, action, action_log_prob = policy.act(rollouts.obs[rollout_step])
        obs, reward, done, info = env.step(action)
        rollouts.add_step(obs, action, action_log_prob, value_pred, reward)

    # Compute expected losses.
    expected_loss_items = get_losses(rollouts, policy, settings)

    # Compute actual losses.
    loss_items = policy.update(rollouts)

    # Compare expected vs. actual.
    for loss_name in ["action", "value", "entropy", "total"]:
        diff = abs(loss_items[loss_name] - expected_loss_items[loss_name])
        print("%s diff: %.5f" % (loss_name, diff))
    assert abs(loss_items["action"] - expected_loss_items["action"]) < TOL
    assert abs(loss_items["value"] - expected_loss_items["value"]) < TOL
    assert abs(loss_items["entropy"] - expected_loss_items["entropy"]) < TOL
    assert abs(loss_items["total"] - expected_loss_items["total"]) < TOL


def get_losses(
    rollouts: RolloutStorage, policy: PPOPolicy, settings: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Computes action, value, entropy, and total loss from rollouts, assuming that we
    aren't performing value loss clipping, and that num_ppo_epochs is 1.

    Parameters
    ----------
    rollouts : RolloutStorage
        Rollout information such as observations, actions, rewards, etc.
    policy : PPOPolicy
        Policy object for training.
    settings : Dict[str, Any]
        Settings dictionary.

    Returns
    -------
    loss_items : Dict[str, float]
        Dictionary holding action, value, entropy, and total loss.
    """

    assert not settings["clip_value_loss"]
    assert settings["num_ppo_epochs"] == 1
    loss_items = {}

    # Compute returns.
    with torch.no_grad():
        rollouts.value_preds[rollouts.rollout_step] = policy.get_value(
            rollouts.obs[rollouts.rollout_step]
        )
    returns = []
    for t in range(settings["rollout_length"]):
        returns.append(0.0)
        for i in range(t, settings["rollout_length"]):
            delta = float(rollouts.rewards[i])
            delta += settings["gamma"] * float(rollouts.value_preds[i + 1])
            delta -= float(rollouts.value_preds[i])
            returns[t] += delta * (settings["gamma"] * settings["gae_lambda"]) ** (
                i - t
            )
        returns[t] += float(rollouts.value_preds[t])

    # Compute advantages.
    advantages = []
    for t in range(settings["rollout_length"]):
        advantages.append(returns[t] - float(rollouts.value_preds[t]))

    if settings["normalize_advantages"]:
        advantage_mean = np.mean(advantages)
        advantage_std = np.std(advantages, ddof=1)
        for t in range(settings["rollout_length"]):
            advantages[t] = (advantages[t] - advantage_mean) / (
                advantage_std + settings["eps"]
            )

    # Compute losses.
    loss_items["action"] = 0.0
    loss_items["value"] = 0.0
    loss_items["entropy"] = 0.0
    entropy = lambda log_probs: sum(-log_prob * exp(log_prob) for log_prob in log_probs)
    clamp = lambda val, min_val, max_val: max(min(val, max_val), min_val)
    for t in range(settings["rollout_length"]):
        with torch.no_grad():
            new_value_pred, new_action_log_probs, new_entropy = policy.evaluate_actions(
                rollouts.obs[t], rollouts.actions[t]
            )
        new_probs = new_action_log_probs.detach().numpy()
        old_probs = rollouts.action_log_probs[t].detach().numpy()
        ratio = np.exp(new_probs - old_probs)
        surrogate1 = ratio * advantages[t]
        surrogate2 = (
            clamp(ratio, 1.0 - settings["clip_param"], 1.0 + settings["clip_param"])
            * advantages[t]
        )
        loss_items["action"] += min(surrogate1, surrogate2)
        loss_items["value"] += 0.5 * (returns[t] - float(new_value_pred)) ** 2
        loss_items["entropy"] += float(new_entropy)

    # Divide to find average.
    loss_items["action"] /= settings["rollout_length"]
    loss_items["value"] /= settings["rollout_length"]
    loss_items["entropy"] /= settings["rollout_length"]

    # Compute total loss.
    loss_items["total"] = -(
        loss_items["action"]
        - settings["value_loss_coeff"] * loss_items["value"]
        + settings["entropy_loss_coeff"] * loss_items["entropy"]
    )

    return loss_items
