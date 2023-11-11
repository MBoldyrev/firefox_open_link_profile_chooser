import configparser
import os
import PySimpleGUI as sg
import re
import subprocess
import sys
import typing
import yaml

from dataclasses import dataclass

CONFIG_FILE = '.firefox_open_link_profile_chooser.yml'

def get_profile_names_from_ff_config(conf_path: str) -> typing.List[str]:
    cp = configparser.ConfigParser()
    cp.read(os.path.join(conf_path, 'profiles.ini'))
    return list(set(s['name'] for s in cp.values() if 'name' in s))


def get_url() -> str:
    return sys.argv[1]


class Rule:
    def test(self) -> bool:
        raise RuntimeError('not implemented')


class RuleAlwaysTrue(Rule):
    def test(self) -> bool:
        return True

class RuleRegexUrl(Rule):
    def __init__(self, pattern: str):
        self.pattern: re.Pattern = re.compile(pattern)

    def test(self) -> bool:
        return self.pattern.search(get_url()) is not None


@dataclass
class Opener:
    def open(self, config: 'Config') -> bool:
        raise RuntimeError('not implemented')

    @staticmethod
    def open_with_profile(profile: str, config: 'Config'):
        args = f'"{" ".join(sys.argv[1:])}"'
        subprocess.run(['i3-msg', 'exec', f'{config.firefox_binary_path} -P {profile} {args}'])


class OpenerFixedProfile(Opener):
    def __init__(self, profile: str):
        self.profile = profile

    def open(self, config: 'Config'):
        self.open_with_profile(self.profile, config)


class OpenerManualChooseProfileBase(Opener):
    @classmethod
    def choose_profile_and_open(cls, profiles_to_choose_from: typing.List[str], config: 'Config'):
        event, _ = sg.Window('choose profile',
                  [[sg.T(f'url: {get_url()}')],
                   *[[sg.B(p)] for p in profiles_to_choose_from]]).read(close=True)
        if event in profiles_to_choose_from:
            cls.open_with_profile(event, config)


class OpenerManualChooseProfileList(OpenerManualChooseProfileBase):
    def __init__(self, profiles_to_choose_from: typing.List[str]):
        self.profiles_to_choose_from = profiles_to_choose_from

    def open(self, config: 'Config'):
        self.choose_profile_and_open(self.profiles_to_choose_from, config)


class OpenerManualChooseProfileAll(OpenerManualChooseProfileBase):
    def open(self, config: 'Config'):
        self.choose_profile_and_open(get_profile_names_from_ff_config(config.firefox_config_dir), config)


@dataclass
class Decider:
    rule: Rule
    opener: Opener


@dataclass
class Config:
    firefox_binary_path: str
    firefox_config_dir: str
    deciders: typing.List[Decider]


def load_config(config_path: str) -> Config:
    def load_rule(src) -> Rule:
        src_type = src['type']
        if src_type == 'url_search_regex':
            return RuleRegexUrl(src['pattern'])
        elif src_type == 'match_all':
            return RuleAlwaysTrue()
        else:
            raise RuntimeError(f'unknown rule type in config: {src_type}')

    def load_opener(src) -> Opener:
        src_type = src['type']
        if src_type == 'fixed':
            return OpenerFixedProfile(src['profile'])
        elif src_type == 'ask_any':
            return OpenerManualChooseProfileAll()
        elif src_type == 'ask_from_list':
            return OpenerManualChooseProfileList(profiles_to_choose_from=src['profiles'])
        else:
            raise RuntimeError(f'unknown rule type in config: {src_type}')

    def load_decider(src) -> Decider:
        return Decider(rule=load_rule(src['rule']), opener=load_opener(src['opener']))

    with open(config_path, 'rt') as inp:
        src = yaml.safe_load(inp)
    return Config(
        firefox_binary_path = src['firefox_binary_path'],
        firefox_config_dir = src['firefox_config_dir'],
        deciders = [load_decider(d_src) for d_src in src['deciders']],
    )

if __name__ == '__main__':
    config_path = os.path.join(os.getenv('HOME'), CONFIG_FILE)
    config = load_config(config_path)
    for decider in config.deciders:
        if decider.rule.test():
            decider.opener.open(config=config)
            break
