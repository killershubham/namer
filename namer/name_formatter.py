import re
import string

from jinja2 import Template
from jinja2.filters import FILTERS


class PartialFormatter(string.Formatter):
    """
    Used for formatting NamerConfig.inplace_name and NamerConfig.
    """

    supported_keys = [
        'date', 'description', 'name', 'site', 'full_site', 'parent', 'full_parent', 'network',
        'full_network', 'performers', 'all_performers', 'performer-sites', 'all_performer-sites',
        'act', 'ext', 'trans', 'source_file_name', 'source_file_stem', 'uuid', '_id', 'vr', 'type', 'year',
        'resolution', 'video_codec', 'audio_codec', 'external_id', 'fps',
    ]

    __regex = {
        's': re.compile(r'.\d+s'),
        'p': re.compile(r'.\d+p'),
        'i': re.compile(r'.\d+i'),
    }

    def __init__(self, missing='~~', bad_fmt='!!'):
        self.missing, self.bad_fmt = missing, bad_fmt
        self.current_field = None
        FILTERS['split'] = str.split

    def get_field(self, field_name, args, kwargs):
        # Store the current field name so format_field knows what it's working on.
        self.current_field = field_name
        
        # Handle a key not found
        try:
            val = super().get_field(field_name, args, kwargs)
        except (KeyError, AttributeError) as err:
            val = None, field_name
            if field_name not in self.supported_keys:
                raise KeyError(f'Key {field_name} not in support keys: {self.supported_keys}') from err

        return val

    def format_field(self, value, format_spec: str):
        if not value:
            return self.missing

        # --- NEW AGGRESSIVE SANITIZATION AND TRUNCATION FOR 'name' FIELD ---
        if isinstance(value, str) and self.current_field == 'name':
            # 1. Aggressively sanitize to remove characters that cause issues on network shares.
            # This whitelist allows: letters, numbers, spaces, hyphens, parentheses, brackets, underscores, periods, commas.
            sanitized_name = re.sub(r'[^a-zA-Z0-9\s\-\(\)\[\]_.,]', '', value)
            # Collapse multiple spaces or hyphens into a single space for cleanliness.
            sanitized_name = re.sub(r'[\s.-]+', ' ', sanitized_name).strip()

            # 2. Truncate the now-safe name to a reasonable length.
            MAX_NAME_LENGTH = 180
            if len(sanitized_name) > MAX_NAME_LENGTH:
                sanitized_name = sanitized_name[:MAX_NAME_LENGTH].strip()
            
            value = sanitized_name  # Use the fully processed name for formatting.

        try:
            if self.__regex['s'].match(format_spec):
                value = value + format_spec[0] * int(format_spec[1:-1])
                format_spec = ''
            elif self.__regex['p'].match(format_spec):
                value = format_spec[0] * int(format_spec[1:-1]) + value
                format_spec = ''
            elif self.__regex['i'].match(format_spec):
                value = format_spec[0] * int(format_spec[1:-1]) + value + format_spec[0] * int(format_spec[1:-1])
                format_spec = ''
            elif format_spec.startswith('|'):
                template = Template(f'{{{{ val{format_spec} }}}}')
                value = template.render(val=value)
                format_spec = ''

            return super().format_field(value, format_spec)
        except ValueError:
            if self.bad_fmt:
                return self.bad_fmt
            raise