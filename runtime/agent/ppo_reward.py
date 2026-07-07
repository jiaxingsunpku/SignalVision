from dataclasses import dataclass
from typing import Mapping, Sequence, Union


Number = Union[int, float]
LaneWaitInput = Union[Mapping[str, Number], Sequence[Number]]


@dataclass(frozen=True)
class GreenRatioRewardConfig:
    """Hyperparameters for the proposed PPO reward shaping."""

    wait_norm: float = 224.0
    wait_clip_min: float = -4.0
    wait_clip_max: float = 4.0
    yellow_time: float = 5.0
    startup_lost_time: float = 2.0
    lambda_switch: float = 0.1
    lambda_green_ratio: float = 0.4


@dataclass(frozen=True)
class GreenRatioRewardBreakdown:
    """Structured reward terms for inspection and logging."""

    mean_waiting_time_count: float
    wait_reward: float
    switched: bool
    previous_green_duration: float
    loss_time: float
    green_ratio_loss: float
    switch_penalty: float
    green_ratio_penalty: float
    total_reward: float


def mean_waiting_time_count(lane_waiting_time_count: LaneWaitInput) -> float:
    """
    Compute the mean waiting-time-count over incoming lanes.

    `lane_waiting_time_count` can be either:
    - a mapping like {"lane_0": 12.0, "lane_1": 5.0}
    - a sequence like [12.0, 5.0]
    """

    if isinstance(lane_waiting_time_count, Mapping):
        values = list(lane_waiting_time_count.values())
    else:
        values = list(lane_waiting_time_count)

    if not values:
        return 0.0
    return float(sum(values) / len(values))


def clipped_wait_reward(
    mean_waiting_time: Number,
    config: GreenRatioRewardConfig = GreenRatioRewardConfig(),
) -> float:
    """
    Reproduce the current PPO wait reward:

        reward = clip(-mean_waiting_time / wait_norm, clip_min, clip_max)
    """

    reward = -float(mean_waiting_time) / config.wait_norm
    return float(min(config.wait_clip_max, max(config.wait_clip_min, reward)))


def effective_switch_loss_time(
    config: GreenRatioRewardConfig = GreenRatioRewardConfig(),
) -> float:
    """Lost time caused by one phase switch."""

    loss_time = config.yellow_time + config.startup_lost_time
    if loss_time < 0:
        raise ValueError("yellow_time + startup_lost_time must be non-negative")
    return float(loss_time)


def green_ratio_loss(
    previous_green_duration: Number,
    config: GreenRatioRewardConfig = GreenRatioRewardConfig(),
) -> float:
    """
    Estimate the green-ratio loss induced by switching away from a phase.

    The loss is:

        L / (g_prev + L)

    where:
    - L: lost time caused by switching
    - g_prev: duration that the previous green has already been held
    """

    g_prev = float(previous_green_duration)
    if g_prev < 0:
        raise ValueError("previous_green_duration must be non-negative")

    loss_time = effective_switch_loss_time(config)
    if loss_time == 0:
        return 0.0
    return float(loss_time / (g_prev + loss_time))


def compute_green_ratio_reward(
    mean_waiting_time: Number,
    switched: bool,
    previous_green_duration: Number,
    config: GreenRatioRewardConfig = GreenRatioRewardConfig(),
) -> GreenRatioRewardBreakdown:
    """
    Compute the proposed composite reward:

        r = r_wait - lambda_switch * I[switch]
                  - lambda_green_ratio * I[switch] * L / (g_prev + L)
    """

    wait_reward = clipped_wait_reward(mean_waiting_time, config)
    loss_time = effective_switch_loss_time(config)

    if switched:
        ratio_loss = green_ratio_loss(previous_green_duration, config)
        switch_penalty = float(config.lambda_switch)
        ratio_penalty = float(config.lambda_green_ratio) * ratio_loss
    else:
        ratio_loss = 0.0
        switch_penalty = 0.0
        ratio_penalty = 0.0

    total_reward = wait_reward - switch_penalty - ratio_penalty

    return GreenRatioRewardBreakdown(
        mean_waiting_time_count=float(mean_waiting_time),
        wait_reward=wait_reward,
        switched=bool(switched),
        previous_green_duration=float(previous_green_duration),
        loss_time=loss_time,
        green_ratio_loss=ratio_loss,
        switch_penalty=switch_penalty,
        green_ratio_penalty=ratio_penalty,
        total_reward=float(total_reward),
    )


def compute_green_ratio_reward_from_lanes(
    lane_waiting_time_count: LaneWaitInput,
    switched: bool,
    previous_green_duration: Number,
    config: GreenRatioRewardConfig = GreenRatioRewardConfig(),
) -> GreenRatioRewardBreakdown:
    """
    Convenience wrapper that starts from per-lane waiting-time-count inputs.
    """

    mean_wait = mean_waiting_time_count(lane_waiting_time_count)
    return compute_green_ratio_reward(
        mean_waiting_time=mean_wait,
        switched=switched,
        previous_green_duration=previous_green_duration,
        config=config,
    )
