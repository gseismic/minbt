import sys
import copy
from loguru import logger as _logger
from typing import Literal, Dict

__all__ = ['create_logger', 'I18nLogger']

def create_logger(name: str="minbt", sink=sys.stdout):
    logger_instance = _logger.bind(name=name)
    logger_instance.remove()
    logger_instance.add(
        sink,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>pid:{process}</cyan>:<cyan>tid:{thread}</cyan> | <level>{message}</level>"
    )
    # logger_instance.name = name # 导致原生的logger无法使用
    return logger_instance


class I18nLogger:

    def __init__(self, logger=None, lang: Literal['zh', 'en'] = 'en', messages: Dict = None):
        self.lang = lang
        self.set_logger(logger)
        self.messages = copy.deepcopy(messages) if messages else {}
    
    def set_lang(self, lang: Literal['zh', 'en']):
        self.lang = lang
    
    def remove(self, *args, **kwargs):
        self.logger.remove(*args, **kwargs)
    
    def add(self, sink, **kwargs):
        """
        e.g.
        logger.add(
            "logs/file_{time}.log",  # 文件路径，{time}会被自动替换为时间戳
            rotation="500 MB",       # 单个文件大小上限
            retention="10 days",     # 日志保留时间
            compression="zip",       # 压缩格式
            encoding="utf-8",        # 编码格式
            level="DEBUG",           # 日志级别
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        )
        """
        self.logger.add(sink, **kwargs)

    def set_logger(self, logger):
        self.logger = logger or create_logger()
        # 原生logger无法使用
        # if logger is not None:
        #     self.name = logger.name
        # else:
        #     self.name = None

    def get_message(self, key: str, *args) -> str:
        msg_template = self.messages[key].get(self.lang, self.messages[key]['en'])
        return msg_template.format(*args)
    
    def debug(self, msg: str, *args):
        if msg in self.messages:
            msg = self.get_message(msg, *args)
        self.logger.debug(msg)

    def info(self, msg: str, *args):
        if msg in self.messages:
            msg = self.get_message(msg, *args)
        self.logger.info(msg)

    def warning(self, msg: str, *args):
        if msg in self.messages:
            msg = self.get_message(msg, *args)
        self.logger.warning(msg)

    def error(self, msg: str, *args):
        if msg in self.messages:
            msg = self.get_message(msg, *args)
        self.logger.error(msg)