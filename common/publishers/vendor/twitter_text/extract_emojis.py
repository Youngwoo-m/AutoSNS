"""공식 twemoji 정규식을 UTF-16 단위로 적용한 뒤 Python 인덱스로 환산한다."""
from .regexp.emoji import emoji


def extract_emojis_with_indices(text):
    units = []
    offsets = [0]
    for index, char in enumerate(text):
        code = ord(char)
        if code > 0xffff:
            code -= 0x10000
            units.extend((chr(0xd800 + (code >> 10)), chr(0xdc00 + (code & 0x3ff))))
            offsets.extend((index, index + 1))
        else:
            units.append(char)
            offsets.append(index + 1)
    result = []
    for match in emoji.finditer(''.join(units)):
        start, end = offsets[match.start()], offsets[match.end()]
        result.append({'emoji': text[start:end], 'indices': [start, end]})
    return result
