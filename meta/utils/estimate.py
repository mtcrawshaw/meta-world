"""
Utility classes to compute running mean and standard deviation of torch.Tensors.
"""

from typing import Tuple

import torch


# This is the number of steps when we start tracking running estimates using an
# exponential moving average instead of an actual arithmetic mean, and the coefficient
# used for EMA.
EMA_THRESHOLD = 100
EMA_ALPHA = 0.99
def single_update(m: torch.Tensor, v: torch.Tensor, n: int) -> torch.Tensor:
    if n <= EMA_THRESHOLD:
        return (m * (n - 1) + v) / n
    else:
        return m * EMA_ALPHA + v * (1. - EMA_ALPHA)


class RunningMean:
    """ Utility class to compute running mean of torch.Tensor. """

    def __init__(self, shape: Tuple[int, ...]) -> None:
        """ Init function for RunningMean. """

        self.num_steps = 0
        self.shape = shape
        self.mean = torch.zeros(*shape)

    def update(self, val: torch.Tensor) -> None:
        """ Update running mean with new value. """

        self.num_steps += 1
        self.mean = single_update(self.mean, val, self.num_steps)


class RunningMeanStdev:
    """
    Utility class to compute running mean and standard deviation of torch.Tensor. We do
    this by keeping a running estimate of the mean and a running estimate of the mean of
    the square, and using the formula `Var[X] = E[X^2] - E[X]^2.
    """

    def __init__(self, shape: Tuple[int, ...]) -> None:
        """ Init function for RunningMeanStd. """

        self.num_steps = 0
        self.shape = shape
        self.mean = torch.zeros(*shape)
        self.square_mean = torch.zeros(*shape)
        self.var = torch.zeros(*shape)
        self.stdev = torch.zeros(*shape)

    def update(self, val: torch.Tensor) -> None:
        """ Update running mean with new value. """

        self.num_steps += 1
        self.mean = single_update(self.mean, val, self.num_steps)
        self.square_mean = single_update(self.square_mean, val ** 2, self.num_steps)
        self.var = self.square_mean - self.mean ** 2
        self.stdev = torch.sqrt(self.var)
