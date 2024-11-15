from .utils.i18n_logger import create_logger, I18nLogger

MESSAGES = {
    '[start_strategy]': {
        'zh': "开始运行策略: {}",
        'en': "Start running strategy: {}"
    },
    '[strategy_complete]': {
        'zh': "策略 {} 运行完成，耗时: {:.2f}秒",
        'en': "Strategy {} completed, time elapsed: {:.2f}s"
    },
    '[start_parallel]': {
        'zh': "开始并行运行 {} 个策略...",
        'en': "Start running {} strategies in parallel..."
    },
    '[all_complete]': {
        'zh': "所有策略运行完成，总耗时: {:.2f}秒",
        'en': "All strategies completed, total time: {:.2f}s"
    },
    '[running_strategies]': {
        'zh': "运行策略",
        'en': "Running strategies"
    }
}

logger = I18nLogger(messages=MESSAGES)
logger.set_logger(create_logger("minbt"))

__all__ = ['logger', 'I18nLogger']