"""
Parse string in to FileNamePart define in namer_types.
"""

from dataclasses import dataclass
import re
from pathlib import PurePath
from typing import List, Optional, Pattern

from loguru import logger

from namer.configuration import NamerConfig
from namer.videophash import PerceptualHash

DEFAULT_REGEX_TOKENS = '{_site}{_sep}{_optional_date}{_ts}{_name}{_dot}{_ext}'


@dataclass(init=False, repr=False, eq=True, order=False, unsafe_hash=True, frozen=False)
class FileInfo:
    """
    Represents info parsed from a file name.
    """
    site: Optional[str] = None
    date: Optional[str] = None
    trans: bool = False
    name: Optional[str] = None
    extension: Optional[str] = None
    source_file_name: Optional[str] = None
    hashes: Optional[PerceptualHash] = None
    jav_code: Optional[str] = None
    code_type: Optional[str] = None
    tpdb_id: Optional[int] = None

    def __str__(self) -> str:
        return f"""site: {self.site}
        date: {self.date}
        trans: {self.trans}
        name: {self.name}
        extension: {self.extension}
        original full name: {self.source_file_name}
        jav_code: {self.jav_code}
        code_type: {self.code_type}
        tpdb_id: {self.tpdb_id}
        hashes: {self.hashes.to_dict() if self.hashes else None}
        """


def name_cleaner(name: str, re_cleanup: List[Pattern]) -> str:
    for regex in re_cleanup:
        name = regex.sub('', name)
    name = name.replace('.', ' ')
    name = ' '.join(name.split()).strip('-')
    return name


def parser_config_to_regex(tokens: str) -> Pattern[str]:
    _sep = r'[\.\- ]+'
    _site = r'(?P<site>.*?)'
    _date = r'(?P<year>[0-9]{2}(?:[0-9]{2})?)[\.\- ]+(?P<month>[0-9]{2})[\.\- ]+(?P<day>[0-9]{2})'
    _optional_date = r'(?:(?P<year>[0-9]{2}(?:[0-9]{2})?)[\.\- ]+(?P<month>[0-9]{2})[\.\- ]+(?P<day>[0-9]{2})[\.\- ]+)?'
    _ts = r'((?P<trans>[T|t][S|s])' + _sep + '){0,1}'
    _name = r'(?P<name>(?:.(?![0-9]{2,4}[\.\- ][0-9]{2}[\.\- ][0-9]{2}))*)'
    _dot = r'\.'
    _ext = r'(?P<ext>[a-zA-Z0-9]{3,4})$'
    regex = tokens.format_map(
        {
            '_site': _site, '_date': _date, '_optional_date': _optional_date, '_ts': _ts,
            '_name': _name, '_ext': _ext, '_sep': _sep, '_dot': _dot,
        }
    )
    return re.compile(regex)


def parse_file_name(filename: str, namer_config: NamerConfig) -> FileInfo:
    file_name_parts = FileInfo()
    file_name_parts.source_file_name = filename
    path = PurePath(filename)
    stem = path.stem
    
    # Use the robustly parsed extension from PurePath
    file_name_parts.extension = path.suffix[1:] if path.suffix else ''

    # --- SUPER-PRIORITY: Look for a TPDB ID tag first ---
    tpdb_regex = re.compile(r'\[(?:the)?porndbid=(\d+)\]', re.IGNORECASE)
    tpdb_match = tpdb_regex.search(stem)
    if tpdb_match:
        file_name_parts.tpdb_id = int(tpdb_match.group(1))
        logger.info('Found ThePornDB ID in filename: {}', file_name_parts.tpdb_id)
        # We have the ID and extension, which is all we need for a direct lookup.
        return file_name_parts

    # --- Original Code Extraction (fallback on the stem) ---
    found_code, code_type = None, None
    forbidden_prefixes = ['WEBDL']
    forbidden_resolutions = ['2160', '1080', '720', '480', '360']
    
    jav_regex = re.compile(r'([a-zA-Z]{2,5}-\d{3,5})', re.IGNORECASE)
    potential_codes = jav_regex.findall(stem)
    if potential_codes:
        for code in potential_codes:
            num_part = code.split('-')[-1]
            if not any(code.upper().startswith(prefix) for prefix in forbidden_prefixes) and num_part not in forbidden_resolutions:
                found_code, code_type = code.upper(), 'JAV'
                break
    
    if not found_code:
        did_milf_regex = re.compile(r'\b((?:did|milf)\-?\d{2,4})\b', re.IGNORECASE)
        match = did_milf_regex.search(stem)
        if match:
            found_code, code_type = match.group(1).lower(), 'SCENE_MOVIE_ID'

    if found_code:
        file_name_parts.jav_code = found_code
        file_name_parts.code_type = code_type
        logger.info('Found External ID code: {} (Type: {})', file_name_parts.jav_code, file_name_parts.code_type)
    
    # Standard name parsing as a final fallback (using original filename for regex).
    filename_with_abbreviations = replace_abbreviations(filename, namer_config)
    regex = parser_config_to_regex(namer_config.name_parser)
    match = regex.search(filename_with_abbreviations)
    if match:
        if match.groupdict().get('year'):
            prefix = '20' if len(match.group('year')) == 2 else ''
            file_name_parts.date = prefix + match.group('year') + '-' + match.group('month') + '-' + match.group('day')
        if match.groupdict().get('name'):
            file_name_parts.name = name_cleaner(match.group('name'), namer_config.re_cleanup)
        if match.groupdict().get('site'):
            file_name_parts.site = match.group('site')
        if match.groupdict().get('trans'):
            trans = match.group('trans')
            file_name_parts.trans = bool(trans and trans.strip().upper() == 'TS')
        # We ignore the regex 'ext' group and stick with our more reliable PurePath extension.
    else:
        logger.debug('Could not parse site/date/name from filename: {}', filename)

    return file_name_parts


def replace_abbreviations(text: str, namer_config: NamerConfig):
    for abbreviation, full in namer_config.site_abbreviations.items():
        if abbreviation.match(text):
            text = abbreviation.sub(full, text, 1)
            break
    return text