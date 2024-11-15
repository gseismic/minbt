import pytest
from minbt.logger import logger, I18nLogger
from minbt.utils.i18n_logger import create_logger

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
    assert 'start_strategy' in logger.messages
    assert 'strategy_complete' in logger.messages
    
    # 测试语言切换
    logger.set_lang('zh')
    assert logger.get_message('start_strategy', 'test') == '开始运行策略: test'
    
    logger.set_lang('en')
    assert logger.get_message('start_strategy', 'test') == 'Start running strategy: test'

def test_create_logger():
    # 测试logger创建函数
    test_logger = create_logger('test')

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

def test_run():
    logger.info("test")
    logger.set_lang("zh")
    logger.info("test")
    logger.info('[start_strategy]', 'test')
    logger.set_lang('en')
    logger.info('[start_strategy]', 'test')
    
if __name__ == "__main__":
    test_run()