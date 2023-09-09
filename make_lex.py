# -*- coding: utf-8 -*-
from __future__ import print_function

import io
import argparse
import re
import time
from collections import defaultdict

# words containing these strings are ignored
wordfilter = ['{', '}', '[', ']', 'PAGENAME', '&lt', '&gt', '&amp', '|', '/', ' ', ':', '*']


def clean_word(word):
    rules = [(',', ''), ('?', ''), ('!', ''), ('.', ''), (u'®', '')]
    for rule in rules:
        word = word.replace(rule[0], rule[1])
    return word


def remove_stress(phonemes):
    return phonemes.replace(u'ˈ', '').replace(u'ˌ', '')


def extract_phonemes(ipa: str, do_remove_stress: bool) -> str:
    """
    Process ipa transcription into a dictionary line.

    """
    if ipa is not None:
        if (not u'…' in ipa) and (not '...' in ipa):
            if do_remove_stress:
                phonemes = remove_stress(ipa)
            phonemes = phonemes.replace(' ', '').replace('.', '').replace('(', '').replace(')',
                                                                                           '').replace(
                '[', '').replace(']', '')
            return phonemes


def title_extractor(line: str, lang: str) -> re.Match:
    if lang == 'de':
        match = re.match('.*==(.*)\(\{\{Sprache\|Deutsch\}\}\) ==', line)
    elif lang == 'en':
        match = re.match('<title>(.*)<\/title>', line)
    elif lang == 'ru':
        match = re.match('<title>(.*)<\/title>', line)
    return match


def ipa_extractor(line: str, source_language:str, target_language: str) -> str:
    """
    Extract IPA transcription from a line.

    """
    if source_language == 'de':
        # same regex for all languages in German
        ipa = re.match('^\:\{\{IPA\}\}.{1,3}\{\{Lautschrift\|([^\}]+)\}\}.*', line.strip())
    elif source_language == 'en':
        # entries are various of this line: * {{a|US}} {{IPA|/ə.bɹʌpt/|/aˈbɹʌpt/|lang=en}}
        uk_test = 'RP' in line or 'UK' in line
        us_test = 'GA' in line or 'US' in line
        ipa = None
        if target_language == 'en-us':
            condition = 'en|' in line and ('IPA' in line or 'IPA-lite' in line) and (
                    (uk_test and us_test) or (us_test and not uk_test) or (not uk_test and not us_test))
        elif target_language == 'en-uk':
            condition = 'en|' in line and ('IPA' in line or 'IPA-lite' in line) and (
                    (uk_test and us_test) or (uk_test and not us_test) or (not uk_test and not us_test))
        elif target_language == 'en':
            condition = 'en|' in line and ('IPA' in line or 'IPA-lite' in line)
        elif target_language == 'de':
            condition = 'de|' in line
        if condition:
            ipa = re.match('^\*{0,3}(?:.*){{[^\/]*\/([^\/]+?)\/[^}]*?}}', line.strip())

    elif source_language == 'ru':
        # {{transcriptions|jaːɐ̯ / jaːr|ˈjaːʁə / jaːrə|De-Jahr.ogg|De-Jahre.ogg}}
        ipa = None
        if 'transcription' in line and '|' in line:
            ipa = re.match('{{[^|]*\|([^|]+?)\|[^}]*?}}', line.strip())
    return ipa


def process(wikifile, outfile, gen_testset, do_remove_stress, source_language, target_language):
    written_out = 0
    time_start = time.time()
    pron_section_start = False
    with io.open(wikifile, 'r', encoding='utf-8') as wiki_in:
        with io.open(outfile, 'w', encoding='utf-8') as wiki_out:
            found_word = False
            for n, line in enumerate(wiki_in):
                if line[-1] == '\n':
                    line = line[:-1]
                line = line.strip()
                # start segment for the dictionary entry
                match = title_extractor(line=line, lang=source_language)
                if ('==English==' in line):
                    found_english = True

                if match:
                    word = match.group(1)
                    word = word.strip()
                    if not any((elem in word for elem in wordfilter)):
                        if len(word) > 20:
                            print(word)
                        if len(word) > 1 and not word[-1] == '-' and not word[0] == '-':
                            word_cleaned = clean_word(word)
                            found_word = True

                if pron_section_start and '===' in line:
                    pron_section_start = False
                if '===Pronunciation===' in line:
                    # sometimes a comment tag has full wiki Markdown code as one line, which breaks the algorithm
                    if '<comment>' in line:
                        continue
                    pron_section_start = True

                ipa = None
                if pron_section_start:
                    ipa = ipa_extractor(line, source_language=source_language, target_language=target_language)

                if found_word and ipa:
                    phonemes = extract_phonemes(ipa.group(1), do_remove_stress)
                    # we identified the word for entry and could parse the phoneme entry:
                    if phonemes:
                        wiki_out.write(word_cleaned + u' ' + u' '.join(phonemes) + '\n')
                        written_out += 1
                        if (written_out % 1000 == 0):
                            print('written: ', written_out, 'entries.')
                            print('%s lines per second.' % (n / (time.time() - time_start)))

                # If we see this somewhere in our input, we are already past the phoneme entry
                if '=See also=' in line or '=Translations=' in line or '</page>' in line or '{{Beispiele}}' in line or '{{Referenzen}}' in line or '{{Quellen}}' in line:
                    found_word=False
                    found_english = False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Process a wiktionary dictionary in xml format and make a text ipa lexicon. Currently for German and English wiktionary XMLs.')
    parser.add_argument('-f', '--file', dest='file', help='process this xml wiktionary lexicon file', type=str,
                        default='dewiktionary-latest-pages-articles-multistream.xml')
    parser.add_argument('-o', '--outfile', dest='outfile', help='lexicon out file', type=str,
                        default='de_ipa_lexicon.txt')
    parser.add_argument('-t', '--gen-testset', dest='gen_testset', help='generate a testset', action='store_true',
                        default=False)
    parser.add_argument('-r', '--remove-stress', dest='remove_stress', help='remove stress markers',
                        action='store_true', default=False)
    parser.add_argument('-l', '--lang', dest='source_language', help='Source dump language', default='de')
    parser.add_argument('-tl', '--target-language', dest='target_language', help='Target language', default='de')
    args = parser.parse_args()
    process(args.file, args.outfile, args.gen_testset, args.remove_stress, args.source_language, args.target_language)
