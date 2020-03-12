import random
from typing import Tuple, Dict

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Categorical
from gym.spaces import Box, Discrete


class ParityEnv:
    """ Environment for testing. Only has two states, and two actions.  """

    def __init__(self) -> None:
        """ Init function for ParityEnv. """

        self.states = [np.array([1, 0]), np.array([0, 1])]
        self.observation_space = Discrete(len(self.states))
        self.action_space = Discrete(len(self.states))
        self.initial_state_index = 0
        self.state_index = self.initial_state_index
        self.state = self.states[self.state_index]

    def reset(self) -> int:
        """ Reset environment to initial state. """

        self.state_index = self.initial_state_index
        self.state = self.states[self.state_index]
        return self.state

    def step(self, action: int) -> Tuple[int, float, bool, dict]:
        """
        Step function for environment. Returns an observation, a reward,
        whether or not the environment is done, and an info dictionary, as is
        the standard for OpenAI gym environments.
        """

        reward = 1 if action == self.state_index else -1
        self.state_index = (self.state_index + 1) % len(self.states)
        self.state = self.states[self.state_index]
        done = False
        info = {}

        return self.state, reward, done, info


class UniqueEnv:
    """ Environment for testing. Each step returns a unique observation and reward. """

    def __init__(self) -> None:
        """ Init function for UniqueEnv. """

        self.observation_space = Box(low=0.0, high=np.inf, shape=(1,))
        self.action_space = Discrete(2)
        self.timestep = 1

    def reset(self) -> float:
        """ Reset environment to initial state. """

        self.timestep = 1
        return float(self.timestep)

    def step(self, action: float) -> Tuple[float, float, bool, dict]:
        """
        Step function for environment. Returns an observation, a reward,
        whether or not the environment is done, and an info dictionary, as is
        the standard for OpenAI gym environments.
        """

        reward = float(self.timestep)
        DONE_TEMP = 10.
        done_prob = 1. - DONE_TEMP / (self.timestep + DONE_TEMP - 1)
        done = random.random() < done_prob
        self.timestep += 1
        obs = float(self.timestep)
        info = {}

        return obs, reward, done, info


class UniquePolicy:
    """
    Policy for testing. Returns a unique action distribution for each observation.
    """

    def __init__(self):
        """ Init function for UniquePolicy. """
        self.policy_network = UniquePolicyNetwork()

    def act(self, obs: float):
        """ Sample action from policy. """

        tensor_obs = torch.Tensor(obs)
        value_pred, action_probs = self.policy_network(tensor_obs)
        action_dist = Categorical(**action_probs)

        action = action_dist.sample()
        action_log_prob = action_dist.log_prob(action)

        # Reshape action_log_prob as in meta/tests/ppo.py.
        if action_log_prob.shape == torch.Size([]):
            action_log_prob = action_log_prob.view(1)
        else:
            pass
            # action_log_prob = action_log_prob.sum(-1)

        return value_pred, action, action_log_prob


class UniquePolicyNetwork(nn.Module):
    """
    Policy network for testing. Returns a unique action distribution for each
    observation.
    """

    def __init__(self):
        """ Init function for UniquePolicyNetwork. """

        super().__init__()
        self.action_probs = lambda obs: [1 / (obs + 1), 1 - 1 / (obs + 1)]

    def forward(self, obs: torch.Tensor) -> Tuple[float, Dict[str, torch.Tensor]]:
        """ Forward pass definition for UniquePolicyNetwork. """

        value_pred = torch.zeros(obs.shape)
        value_pred.copy_(obs)
        probs = torch.cat(self.action_probs(obs))
        action_probs = {"probs": probs}

        return value_pred, action_probs