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
                ipa = remove_stress(ipa)
            phonemes = ipa.replace(' ', '').replace('.', '').replace('(', '').replace(')',
                                                                                      '').replace(
                '[', '').replace(']', '')
            return phonemes
    return ''


def title_extractor(line: str, lang: str, target_language: str) -> re.Match:
    if lang == 'de':
        if target_language == 'de':
            match = re.match(r'.*==(.*)\(\{\{Sprache\|Deutsch\}\}\) ==', line)
        elif 'en' in target_language:
            match = re.match(r'.*==(.*)\(\{\{Sprache\|Englisch\}\}\) ==', line)
        elif 'la' in target_language:
            match = re.match(r'.*==(.*)\(\{\{Sprache\|Latein\}\}\) ==', line)

    elif lang in ('en','ru','fr') :
        match = re.match(r'<title>(.*)<\/title>', line)

    return match


def ipa_extractor(line: str, source_language: str, target_language: str) -> re.Match:
    """
    Extract IPA transcription from a line.

    """
    ipa = None
    if source_language == 'de':
        # same regex for all languages in German
        if not 'spr=' in line:
            ipa = re.match(r'^\:\{\{IPA\}\}.{1,3}\{\{Lautschrift\|([^\}]+)\}\}.*', line.strip())
    elif source_language == 'en':
        # entries are various of this line: * {{a|US}} {{IPA|/ə.bɹʌpt/|/aˈbɹʌpt/|lang=en}}
        uk_test = 'RP' in line or 'UK' in line
        us_test = 'GA' in line or 'US' in line

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
            ipa = re.match(r'^\*{0,3}(?:.*){{[^\/]*\/([^\/]+?)\/[^}]*?}}', line.strip())

    elif source_language == 'ru':
        # {{transcriptions|jaːɐ̯ / jaːr|ˈjaːʁə / jaːrə|De-Jahr.ogg|De-Jahre.ogg}}
        ipa = None
        if 'transcription' in line and '|' in line:
            ipa = re.match(r'{{[^|]*\|([^|]+?)\|[^}]*?}}', line.strip())
    elif source_language == 'fr':

        ipa = re.match(r"'''\w+''' {{[^\|]*\|([^\|]+?)\|%s}}" % target_language, line.strip())
        if ipa:
            print(ipa,line)
    return ipa


def end_of_tag_condition(line, source_language):
    if '</page>' in line:
        return True

    if source_language == 'en':
        return '=See also=' in line or '=Translations=' in line

    if source_language == 'de':
        return any(keyword in line for keyword in ['{{Beispiele}}', '{{Referenzen}}', '{{Quellen}}'])

    if source_language == 'ru':
        return any(keyword in line for keyword in
                   ['=== Семантические свойства ===', '==== Значение ====', '=== Родственные слова ==='])

    if source_language == 'fr':
        return any(keyword in line for keyword in
                   ['==== {{S|synonymes}} ====', '=== {{S|références}} ===', '===== {{S|dérivés}} ===='])

    return False


def pronunciation_section_condition(pron_section_start, line: str, source_language: str):
    if pron_section_start:
        # we encounter next section symbols, so pronunciation section ends
        if source_language in ('en', 'ru'):
            if line.startswith('==='):
                return False
    # we encounter pronunciation section symbols, so pronunciation section starts
    if source_language == 'en':
        if '===Pronunciation===' in line:
            pron_section_start = True
    elif source_language == 'ru':
        if '=== Произношение ===' in line:
            pron_section_start = True
    return pron_section_start


def process(wikifile, outfile, gen_testset, do_remove_stress, source_language, target_language):
    written_out = 0
    time_start = time.time()
    pron_section_started = False
    found_english = False
    word_language_status = False
    if not outfile:
        outfile = f'{target_language}_IN_{source_language}.txt'
    with io.open(wikifile, 'r', encoding='utf-8') as wiki_in:
        with io.open(outfile, 'w', encoding='utf-8') as wiki_out:
            found_word = False
            for n, line in enumerate(wiki_in):
                if line[-1] == '\n':
                    line = line[:-1]
                line = line.strip()

                # start segment for the dictionary entry
                match = title_extractor(line=line, lang=source_language, target_language=target_language)

                if match:
                    word = match.group(1)
                    word = word.strip()
                    if not any((elem in word for elem in wordfilter)):
                        if len(word) > 20:
                            1  # print(word)
                        if len(word) > 1 and not word[-1] == '-' and not word[0] == '-':
                            word_cleaned = clean_word(word)
                            found_word = True

                # sometimes a comment tag has full wiki Markdown code as one line, which breaks the algorithm
                if '<comment>' in line:
                    continue

                def language_extractor(line, target_language, source_language):
                    # Extract entry language name from the line.
                    if source_language == 'ru':
                        match = re.search(r'()(= {{-([a-z]{2,3})-\|?.*?}} =)', line)
                        if match:
                            word_language = match.group(3)
                            if word_language == target_language:
                                return True
                    elif source_language == 'fr':
                        match = re.search(r'== {{langue\|([a-z]{1,3})}}', line)
                        if match:
                            word_language = match.group(1)
                            if word_language == target_language:
                                return True
                    else:
                        return True

                if not word_language_status:
                    word_language_status = language_extractor(line, target_language, source_language)

                pron_section_started = pronunciation_section_condition(pron_section_started, line=line,
                                                                       source_language=source_language)
                ipa = None
                if ((source_language in ('en', 'ru') and pron_section_started) or (
                        not source_language in ('en', 'ru'))) and word_language_status:
                    ipa = ipa_extractor(line, source_language=source_language, target_language=target_language)

                if found_word and ipa:
                    phonemes = extract_phonemes(ipa.group(1), do_remove_stress)
                    # we identified the word for entry and could parse the phoneme entry:
                    if phonemes:
                        wiki_out.write(word_cleaned + u' ' + u' '.join(phonemes) + '\n')
                        written_out += 1
                        found_english = False
                        if (written_out % 1000 == 0):
                            print('written: ', written_out, 'entries.')
                            print('%s lines per second.' % (n / (time.time() - time_start)))

                # If we see this somewhere in our input, we are already past the phoneme entry
                if end_of_tag_condition(line, source_language):
                    found_word = False
                    found_english = False
                    word_language_status = False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Process a wiktionary dictionary in xml format and make a text ipa lexicon. Currently for German and English wiktionary XMLs.')
    parser.add_argument('-f', '--file', dest='file', help='process this xml wiktionary lexicon file', type=str,
                        default='dewiktionary-latest-pages-articles-multistream.xml')
    parser.add_argument('-o', '--outfile', dest='outfile', help='lexicon out file', type=str,
                        default=None)
    parser.add_argument('-t', '--gen-testset', dest='gen_testset', help='generate a testset', action='store_true',
                        default=False)
    parser.add_argument('-r', '--remove-stress', dest='remove_stress', help='remove stress markers',
                        action='store_true', default=False)
    parser.add_argument('-l', '--lang', dest='source_language', help='Source dump language', default='de')
    parser.add_argument('-tl', '--target-language', dest='target_language', help='Target language', default='de')
    args = parser.parse_args()
    process(args.file, args.outfile, args.gen_testset, args.remove_stress, args.source_language, args.target_language)
