""" Utility functions and objects for training pipeline. """

import os
from functools import reduce
from typing import Dict, List, Union, Tuple, Any
import pickle

import numpy as np
import torch
import torch.nn as nn
import gym
from gym import Env
from gym.spaces import Space, Box, Discrete
from baselines import bench
from baselines.common.running_mean_std import RunningMeanStd

from meta.tests.envs import ParityEnv, UniqueEnv


METRICS_DIR = os.path.join("data", "metrics")


class AddBias(nn.Module):
    """ Hacky fix for Gaussian policies. """
    def __init__(self, bias: torch.Tensor) -> None:
        super(AddBias, self).__init__()
        self._bias = nn.Parameter(bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self._bias


def init(
    module: nn.Module, weight_init: Any, bias_init: Any, gain: Union[float, int] = 1
) -> nn.Module:
    """ Helper function to initialize network weights. """

    weight_init(module.weight.data, gain=gain)
    bias_init(module.bias.data)
    return module


def get_space_size(space: Space) -> int:
    """ Get the input/output size of an MLP whose input/output space is ``space``. """

    size: int = 0
    if isinstance(space, Discrete):
        size = space.n
    elif isinstance(space, Box):
        size = reduce(lambda a, b: a * b, space.shape)
    else:
        raise ValueError("Unsupported space type: %s." % type(space))

    return size


def compare_metrics(
    metrics: Dict[str, List[float]], metrics_filename: str
) -> Tuple[Any, bool]:
    """ Compute diff of metrics against the most recently saved baseline. """

    # Load baseline metric values.
    with open(metrics_filename, "rb") as metrics_file:
        baseline_metrics = pickle.load(metrics_file)

    # Compare metrics against baseline.
    assert set(metrics.keys()) == set(baseline_metrics.keys())
    diff: Dict[str, List[Any]] = {key: [] for key in metrics}
    for key in metrics:
        assert len(metrics[key]) == len(baseline_metrics[key])

        for i in range(max(len(metrics[key]), len(baseline_metrics[key]))):

            if i >= len(metrics[key]):
                diff[key].append((i, None, baseline_metrics[key][i]))
            if i >= len(baseline_metrics[key]):
                diff[key].append((i, metrics[key][i], None))

            current_val = metrics[key][i]
            baseline_val = baseline_metrics[key][i]
            if current_val != baseline_val:
                diff[key].append((i, current_val, baseline_val))

    print("Metrics diff: %s" % diff)
    assert all(len(diff_values) == 0 for diff_values in diff.values())


def get_env(
    env_name: str,
    seed: int = 1,
    normalize: bool = True,
    allow_early_resets: bool = False,
) -> Env:
    """
    Return environment object from environment name.

    Parameters
    ----------
    env_name : str
        Name of environment to create.
    seed : int
        Random seed for environment.
    normalize : bool
        Whether or not to add environment wrapper to normalize observations and rewards.
    allow_early_resets: bool
        Whether or not to allow environments before done=True is returned.

    Returns
    -------
    env : Env
        Environment object.
    """

    # Make environment object from either MetaWorld or Gym.
    metaworld_env_names = get_metaworld_env_names()
    if env_name in metaworld_env_names:

        # We import here so that we avoid importing metaworld if possible, since it is
        # dependent on mujoco.
        from metaworld.benchmarks import ML1

        env = ML1.get_train_tasks(env_name)
        tasks = env.sample_tasks(1)
        env.set_task(tasks[0])

    elif env_name == "unique-env":
        env = UniqueEnv()

    elif env_name == "parity-env":
        env = ParityEnv()

    else:
        env = gym.make(env_name)

    # Set environment seed.
    env.seed(seed)

    # Add environment wrappers.
    env = bench.Monitor(env, None, allow_early_resets=allow_early_resets)
    if normalize:
        env = NormalizeEnv(env)
    env = PyTorchEnv(env)

    return env


class PyTorchEnv(gym.Wrapper):
    """
    Environment wrapper to convert observations, actions and rewards to torch.Tensors.
    """

    def reset(self) -> torch.Tensor:
        obs = self.env.reset()
        obs = torch.from_numpy(obs).float()
        return obs

    def step(
        self, action: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, bool, Dict[str, Any]]:
        if isinstance(action, torch.LongTensor):
            # Squeeze the dimension for discrete actions
            action = action.squeeze(0)

        # Convert action to numpy or singleton float/int.
        if isinstance(self.action_space, Discrete):
            if isinstance(action, torch.LongTensor):
                action = int(action.cpu())
            else:
                action = float(action.cpu())
        else:
            action = action.cpu().numpy()

        obs, reward, done, info = self.env.step(action)
        obs = torch.from_numpy(obs).float()
        reward = torch.Tensor([reward]).float()

        return obs, reward, done, info


class NormalizeEnv(gym.Wrapper):
    """ Environment wrapper to normalize observations and returns. """

    def __init__(
        self,
        env: Env,
        clip_ob: float = 10.0,
        clip_rew: float = 10.0,
        gamma: float = 0.99,
        epsilon: float = 1e-8,
    ) -> None:

        super().__init__(env)

        # Save state.
        self.clip_ob = clip_ob
        self.clip_rew = clip_rew
        self.gamma = gamma
        self.epsilon = epsilon

        # Create running estimates of observation/return mean and standard deviation,
        # and a float to store the sum of discounted rewards.
        self.ob_rms = RunningMeanStd(shape=self.observation_space.shape)
        self.ret_rms = RunningMeanStd(shape=())
        self.ret = np.zeros(1)

        # Start in training mode.
        self.training = True

    def reset(self) -> np.ndarray:
        self.ret = np.zeros(1)
        obs = self.env.reset()
        return self._obfilt(obs)

    def step(
        self, action: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, bool, Dict[str, Any]]:

        obs, reward, done, info = self.env.step(action)
        if done:
            obs = self.env.reset()

        self.ret = self.ret * self.gamma + reward
        obs = self._obfilt(obs)
        self.ret_rms.update(np.array(self.ret))
        reward = np.clip(
            reward / np.sqrt(self.ret_rms.var + self.epsilon),
            -self.clip_rew,
            self.clip_rew,
        )

        if done:
            self.ret = np.zeros(1)

        return obs, reward, done, info

    def _obfilt(self, obs: np.ndarray, update: bool = True) -> np.ndarray:

        if self.ob_rms:
            if update:
                self.ob_rms.update(np.expand_dims(obs, axis=0))
            obs = np.clip(
                (obs - self.ob_rms.mean) / np.sqrt(self.ob_rms.var + self.epsilon),
                -self.clip_ob,
                self.clip_ob,
            )

        return obs


def get_metaworld_env_names() -> List[str]:
    """ Returns a list of Metaworld environment names. """

    return HARD_MODE_CLS_DICT["train"] + HARD_MODE_CLS_DICT["test"]


# HARDCODE. This is copied from the metaworld repo to avoid the need to import metaworld
# unnencessarily. Since it relies on mujoco, we don't want to import it if we don't have
# to.
HARD_MODE_CLS_DICT = {
    "train": [
        "reach-v1",
        "push-v1",
        "pick-place-v1",
        "reach-wall-v1",
        "pick-place-wall-v1",
        "push-wall-v1",
        "door-open-v1",
        "door-close-v1",
        "drawer-open-v1",
        "drawer-close-v1",
        "button-press_topdown-v1",
        "button-press-v1",
        "button-press-topdown-wall-v1",
        "button-press-wall-v1",
        "peg-insert-side-v1",
        "peg-unplug-side-v1",
        "window-open-v1",
        "window-close-v1",
        "dissassemble-v1",
        "hammer-v1",
        "plate-slide-v1",
        "plate-slide-side-v1",
        "plate-slide-back-v1",
        "plate-slide-back-side-v1",
        "handle-press-v1",
        "handle-pull-v1",
        "handle-press-side-v1",
        "handle-pull-side-v1",
        "stick-push-v1",
        "stick-pull-v1",
        "basket-ball-v1",
        "soccer-v1",
        "faucet-open-v1",
        "faucet-close-v1",
        "coffee-push-v1",
        "coffee-pull-v1",
        "coffee-button-v1",
        "sweep-v1",
        "sweep-into-v1",
        "pick-out-of-hole-v1",
        "assembly-v1",
        "shelf-place-v1",
        "push-back-v1",
        "lever-pull-v1",
        "dial-turn-v1",
    ],
    "test": [
        "bin-picking-v1",
        "box-close-v1",
        "hand-insert-v1",
        "door-lock-v1",
        "door-unlock-v1",
    ],
}
