#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vocabulary Processing Pipeline
Consolidates words from multiple sources and enriches with dictionary data
"""

import json
import re
from collections import defaultdict
from pathlib import Path
import time

class VocabularyProcessor:
    def __init__(self, sources_dir='data/sources', output_dir='data/processed'):
        self.sources_dir = Path(sources_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.word_index = defaultdict(lambda: {
            'sources': [],
            'pos_tags': set(),
            'chinese_defs': set(),
            'examples': [],
            'categories': set()
        })

    def normalize_key(self, word):
        """Normalize word to canonical form for deduplication"""
        return word.strip().lower()

    def parse_pipe_delimited(self, filepath):
        """Parse pipe-delimited vocabulary files (source1 & source2)"""
        current_category = None

        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith('+++') or line.startswith('---'):
                    continue

                if '|' not in line:
                    current_category = line
                    continue

                parts = line.split('|')
                if len(parts) < 2:
                    continue

                word = parts[0].strip()
                if not word:
                    continue

                key = self.normalize_key(word)

                pos = parts[1].strip() if len(parts) > 1 else ''
                chinese_def = parts[2].strip() if len(parts) > 2 else ''
                example = parts[3].strip() if len(parts) > 3 else ''

                entry = self.word_index[key]
                entry['sources'].append(filepath.name)
                if pos:
                    entry['pos_tags'].add(pos)
                if chinese_def:
                    entry['chinese_defs'].add(chinese_def)
                if example:
                    entry['examples'].append(example)
                if current_category:
                    entry['categories'].add(current_category)

    def parse_listening_json(self, filepath):
        """Parse listening179.json"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for item in data:
            word = item.get('word', '').strip()
            if not word:
                continue

            key = self.normalize_key(word)
            entry = self.word_index[key]
            entry['sources'].append(filepath.name)

            if item.get('type'):
                entry['pos_tags'].add(item['type'])
            if item.get('meaning'):
                entry['chinese_defs'].add(item['meaning'])
            if item.get('replace'):
                entry['synonyms'] = item['replace']

    def parse_reading_js(self, filepath):
        """Parse reading538words.js"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r'\[(\d+),\s*"([^"]+)"'
        matches = re.findall(pattern, content)

        for idx, word in matches:
            key = self.normalize_key(word)
            entry = self.word_index[key]
            entry['sources'].append(filepath.name)
            entry['categories'].add('reading')

    def load_all_sources(self):
        """Load and consolidate all vocabulary sources"""
        print("Loading vocabulary sources...")

        source1 = self.sources_dir / 'vocab_source1.txt'
        if source1.exists():
            print(f"  Loading {source1.name}...")
            self.parse_pipe_delimited(source1)

        source2 = self.sources_dir / 'vocab_source2.txt'
        if source2.exists():
            print(f"  Loading {source2.name}...")
            self.parse_pipe_delimited(source2)

        listening = self.sources_dir / 'vocab_listening179.json'
        if listening.exists():
            print(f"  Loading {listening.name}...")
            self.parse_listening_json(listening)

        reading = self.sources_dir / 'vocab_reading538.js'
        if reading.exists():
            print(f"  Loading {reading.name}...")
            self.parse_reading_js(reading)

        print(f"\nConsolidated {len(self.word_index)} unique words")

    def export_word_list(self):
        """Export consolidated word list"""
        output_file = self.output_dir / 'consolidated_words.json'

        consolidated = {}
        for word, data in self.word_index.items():
            consolidated[word] = {
                'sources': list(set(data['sources'])),
                'pos_tags': list(data['pos_tags']),
                'chinese_defs': list(data['chinese_defs']),
                'examples': data['examples'],
                'categories': list(data['categories']),
                'source_count': len(set(data['sources']))
            }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(consolidated, f, ensure_ascii=False, indent=2)

        print(f"Exported consolidated word list to {output_file}")
        return consolidated

    def fetch_dictionary_data(self, word):
        """
        Fetch authoritative dictionary data for a word
        Using Free Dictionary API as initial implementation
        """
        import subprocess

        try:
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
            result = subprocess.run(
                ['curl', '-s', url],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                return data
            return None
        except Exception as e:
            return None

    def enrich_with_dictionary(self, sample_size=None):
        """
        Enrich words with dictionary data
        sample_size: number of words to process (None = all words)
        """
        words_to_process = list(self.word_index.keys()) if sample_size is None else list(self.word_index.keys())[:sample_size]
        print(f"\nEnriching words with dictionary data ({len(words_to_process)} words)...")

        enriched = {}

        for i, word in enumerate(words_to_process, 1):
            if i % 100 == 0:
                print(f"  [{i}/{len(words_to_process)}] Progress...")

            dict_data = self.fetch_dictionary_data(word)
            if dict_data:
                enriched[word] = {
                    'original_data': {
                        'sources': list(set(self.word_index[word]['sources'])),
                        'pos_tags': list(self.word_index[word]['pos_tags']),
                        'chinese_defs': list(self.word_index[word]['chinese_defs']),
                        'examples': self.word_index[word]['examples'],
                        'categories': list(self.word_index[word]['categories'])
                    },
                    'dictionary': dict_data
                }
                time.sleep(0.5)

        output_file = self.output_dir / ('enriched_all.json' if sample_size is None else 'enriched_sample.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(enriched, f, ensure_ascii=False, indent=2)

        print(f"\nEnriched {len(enriched)} words, saved to {output_file}")
        return enriched

def main():
    processor = VocabularyProcessor()

    processor.load_all_sources()

    consolidated = processor.export_word_list()

    print("\n=== Statistics ===")
    multi_source = sum(1 for w in consolidated.values() if w['source_count'] > 1)
    print(f"Words from multiple sources: {multi_source}")
    print(f"Words with examples: {sum(1 for w in consolidated.values() if w['examples'])}")
    print(f"Words with Chinese definitions: {sum(1 for w in consolidated.values() if w['chinese_defs'])}")

    print("\n=== Enriching All Words with Dictionary API ===")
    processor.enrich_with_dictionary(sample_size=None)

if __name__ == '__main__':
    main()
