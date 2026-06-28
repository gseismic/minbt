import os
import subprocess
import sys
from pathlib import Path

import pytest
from minbt.logger import logger, I18nLogger
from minbt.utils.i18n_logger import create_logger


class CaptureLogger:
    def __init__(self):
        self.records = []

    def debug(self, msg):
        self.records.append(('debug', msg))

    def info(self, msg):
        self.records.append(('info', msg))

    def warning(self, msg):
        self.records.append(('warning', msg))

    def error(self, msg):
        self.records.append(('error', msg))

    def remove(self, *args, **kwargs):
        pass

    def add(self, *args, **kwargs):
        pass

def test_i18n_logger_basic():
    # 测试基本的日志创建
    test_logger = I18nLogger()
    assert test_logger.lang == 'en'
    assert test_logger.messages == {}

def test_i18n_logger_messages():
    # 测试带消息的日志
    messages = {
        'test_msg': {
            'zh': '测试消息 {}',
            'en': 'Test message {}'
        }
    }
    test_logger = I18nLogger(messages=messages)
    
    # 测试英文消息
    assert test_logger.get_message('test_msg', 'hello') == 'Test message hello'
    
    # 测试中文消息
    test_logger.set_lang('zh')
    assert test_logger.get_message('test_msg', 'hello') == '测试消息 hello'

def test_logger_instance():
    # 测试全局logger实例
    assert logger.lang == 'en'
    assert '[start_strategy]' in logger.messages
    assert '[strategy_complete]' in logger.messages
    
    # 测试语言切换
    logger.set_lang('zh')
    assert logger.get_message('[start_strategy]', 'test') == '开始运行策略: test'
    
    logger.set_lang('en')
    assert logger.get_message('[start_strategy]', 'test') == 'Start running strategy: test'

def test_create_logger_does_not_add_sink_by_default():
    # 测试logger创建函数默认不修改全局 loguru sink
    before_handlers = set(logger.logger._core.handlers)
    test_logger = create_logger('test')
    after_handlers = set(logger.logger._core.handlers)

    assert test_logger is not None
    assert after_handlers == before_handlers


def test_create_logger_adds_sink_when_explicit():
    records = []
    before_handlers = set(logger.logger._core.handlers)
    test_logger = create_logger('test', sink=lambda message: records.append(str(message)))
    new_handlers = set(logger.logger._core.handlers) - before_handlers
    try:
        test_logger.info('explicit sink')
    finally:
        for handler_id in new_handlers:
            logger.logger.remove(handler_id)

    assert len(new_handlers) == 1
    assert any('explicit sink' in record for record in records)


def test_minbt_logger_import_does_not_add_loguru_sink():
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env['PYTHONPATH'] = str(repo_root) + os.pathsep + env.get('PYTHONPATH', '')
    code = """
from loguru import logger as raw_logger
before = len(raw_logger._core.handlers)
import minbt.logger
after = len(raw_logger._core.handlers)
raise SystemExit(0 if before == after else 1)
"""

    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_create_logger_does_not_remove_existing_loguru_sinks():
    records = []
    sink_id = logger.logger.add(lambda message: records.append(str(message)))
    try:
        create_logger('test')
        logger.logger.info('external sink still active')
    finally:
        logger.logger.remove(sink_id)

    assert any('external sink still active' in record for record in records)


def test_i18n_logger_methods():
    # 测试各种日志级别方法
    messages = {
        'test_msg': {
            'zh': '测试消息',
            'en': 'Test message'
        }
    }
    test_logger = I18nLogger(messages=messages)
    
    # 测试不同的日志级别
    test_logger.debug('test_msg')
    test_logger.info('test_msg')
    test_logger.warning('test_msg')
    test_logger.error('test_msg')
    
    # 测试直接消息
    test_logger.info('Direct message')

def test_i18n_logger_formats_plain_message_args():
    capture = CaptureLogger()
    test_logger = I18nLogger(logger=capture)

    test_logger.info('Hello {}', 'world')
    test_logger.info('on_data', {'symbol': 'AAPL', 'close': 100})

    assert capture.records[0] == ('info', 'Hello world')
    assert capture.records[1] == ('info', "on_data {'symbol': 'AAPL', 'close': 100}")

def test_i18n_logger_formats_i18n_kwargs():
    capture = CaptureLogger()
    messages = {
        'test_msg': {
            'zh': '测试消息 {value}',
            'en': 'Test message {value}'
        }
    }
    test_logger = I18nLogger(logger=capture, messages=messages)

    test_logger.info('test_msg', value='hello')

    assert capture.records == [('info', 'Test message hello')]

def test_run():
    logger.info("test")
    logger.set_lang("zh")
    logger.info("test")
    logger.info('[start_strategy]', 'test')
    logger.set_lang('en')
    logger.info('[start_strategy]', 'test')
    
if __name__ == "__main__":
    test_run()
