# -*- coding: utf-8 -*-
"""Implementation of Rapid Automatic Keyword Extraction algorithm.

As described in the paper `Automatic keyword extraction from individual
documents` by Stuart Rose, Dave Engel, Nick Cramer and Wendy Cowley.
"""

import string
from collections import Counter, defaultdict
from itertools import chain, groupby, product

import nltk
from enum import Enum
from nltk.tokenize import wordpunct_tokenize
import re


class Metric(Enum):
    """Different metrics that can be used for ranking."""

    DEGREE_TO_FREQUENCY_RATIO = 0  # Uses d(w)/f(w) as the metric
    WORD_DEGREE = 1  # Uses d(w) alone as the metric
    WORD_FREQUENCY = 2  # Uses f(w) alone as the metric


class Rake(object):
    """Rapid Automatic Keyword Extraction Algorithm."""

    def __init__(
        self,
        stopwords=None,
        punctuations_allowed='',
        tokenizer=None,
        language="english",
        ranking_metric=Metric.DEGREE_TO_FREQUENCY_RATIO,
        max_length=100000,
        min_length=1,
    ):
        """Constructor.

        :param stopwords: List of Words to be ignored for keyword extraction.
        :param punctuations_allowed: Punctuations that will be explicitly not ignored
        :param language: Language to be used for stopwords
        :param max_length: Maximum limit on the number of words in a phrase
                           (Inclusive. Defaults to 100000)
        :param min_length: Minimum limit on the number of words in a phrase
                           (Inclusive. Defaults to 1)
        """
        # By default use degree to frequency ratio as the metric.
        if isinstance(ranking_metric, Metric):
            self.metric = ranking_metric
        else:
            self.metric = Metric.DEGREE_TO_FREQUENCY_RATIO

        # If stopwords not provided we use language stopwords by default.
        self.stopwords = stopwords
        if self.stopwords is None:
            self.stopwords = nltk.corpus.stopwords.words(language)

        #string.translate only works in Python3
        allowed_chars = 'a-zA-Z0-9_'
        self.punctuation_regex = re.compile('[^' + ''.join([allowed_chars, re.escape(punctuations_allowed)]) + ']')


        # Let user provide a tokenizer
        self.tokenizer = tokenizer
        if self.tokenizer is None:
            self.tokenizer = wordpunct_tokenize

        # Assign min or max length to the attributes
        self.min_length = min_length
        self.max_length = max_length

        # Stuff to be extracted from the provided text.
        self.frequency_dist = None
        self.degree = None
        self.rank_list = None
        self.ranked_phrases = None

    def extract_keywords_from_text(self, text):
        """Method to extract keywords from the text provided.

        :param text: Text to extract keywords from, provided as a string.
        """
        sentences = nltk.tokenize.sent_tokenize(text)
        self.extract_keywords_from_sentences(sentences)

    def extract_keywords_from_sentences(self, sentences):
        """Method to extract keywords from the list of sentences provided.

        :param sentences: Text to extraxt keywords from, provided as a list
                          of strings, where each string is a sentence.
        """
        phrase_list = self._generate_phrases(sentences)
        self._build_frequency_dist(phrase_list)
        self._build_word_co_occurance_graph(phrase_list)
        self._build_ranklist(phrase_list)

    def get_ranked_phrases(self):
        """Method to fetch ranked keyword strings.

        :return: List of strings where each string represents an extracted
                 keyword string.
        """
        return self.ranked_phrases

    def get_ranked_phrases_with_scores(self):
        """Method to fetch ranked keyword strings along with their scores.

        :return: List of tuples where each tuple is formed of an extracted
                 keyword string and its score. Ex: (5.68, 'Four Scoures')
        """
        return self.rank_list

    def get_word_frequency_distribution(self):
        """Method to fetch the word frequency distribution in the given text.

        :return: Dictionary (defaultdict) of the format `word -> frequency`.
        """
        return self.frequency_dist

    def get_word_degrees(self):
        """Method to fetch the degree of words in the given text. Degree can be
        defined as sum of co-occurances of the word with other words in the
        given text.

        :return: Dictionary (defaultdict) of the format `word -> degree`.
        """
        return self.degree

    def _build_frequency_dist(self, phrase_list):
        """Builds frequency distribution of the words in the given body of text.

        :param phrase_list: List of List of strings where each sublist is a
                            collection of words which form a contender phrase.
        """
        self.frequency_dist = Counter(chain.from_iterable(phrase_list))

    def _build_word_co_occurance_graph(self, phrase_list):
        """Builds the co-occurance graph of words in the given body of text to
        compute degree of each word.

        :param phrase_list: List of List of strings where each sublist is a
                            collection of words which form a contender phrase.
        """
        co_occurance_graph = defaultdict(lambda: defaultdict(lambda: 0))
        for phrase in phrase_list:
            # For each phrase in the phrase list, count co-occurances of the
            # word with other words in the phrase.
            #
            # Note: Keep the co-occurances graph as is, to help facilitate its
            # use in other creative ways if required later.
            for (word, coword) in product(phrase, phrase):
                co_occurance_graph[word][coword] += 1
        self.degree = defaultdict(lambda: 0)
        for key in co_occurance_graph:
            self.degree[key] = sum(co_occurance_graph[key].values())

    def _build_ranklist(self, phrase_list):
        """Method to rank each contender phrase using the formula

              phrase_score = sum of scores of words in the phrase.
              word_score = d(w)/f(w) where d is degree and f is frequency.

        :param phrase_list: List of List of strings where each sublist is a
                            collection of words which form a contender phrase.
        """
        self.rank_list = []
        for phrase in phrase_list:
            rank = 0.0
            for word in phrase:
                if self.metric == Metric.DEGREE_TO_FREQUENCY_RATIO:
                    rank += 1.0 * self.degree[word] / self.frequency_dist[word]
                elif self.metric == Metric.WORD_DEGREE:
                    rank += 1.0 * self.degree[word]
                else:
                    rank += 1.0 * self.frequency_dist[word]
            self.rank_list.append((rank, " ".join(phrase)))
        self.rank_list.sort(reverse=True)
        self.ranked_phrases = [ph[1] for ph in self.rank_list]

    def _generate_phrases(self, sentences):
        """Method to generate contender phrases given the sentences of the text
        document.

        :param sentences: List of strings where each string represents a
                          sentence which forms the text.
        :return: Set of string tuples where each tuple is a collection
                 of words forming a contender phrase.
        """
        phrase_list = set()
        # Create contender phrases from sentences.
        for sentence in sentences:
            word_list = [word.lower() for word in self.tokenizer(sentence)]
            phrase_list.update(self._get_phrase_list_from_words(word_list))
        return phrase_list

    def _confirm_word_validity(self, word):
        """ Remove if the word has a punctuation in it that we should split on
            OR, if the word is in stop words,
        """
        if self.punctuation_regex.search(word):
            return False
        return word not in self.stopwords



    def _get_phrase_list_from_words(self, word_list):
        """Method to create contender phrases from the list of words that form
        a sentence by dropping stopwords and punctuations and grouping the left
        words into phrases. Only phrases in the given length range (both limits
        inclusive) would be considered to build co-occurrence matrix. Ex:

        Sentence: Red apples, are good in flavour.
        List of words: ['red', 'apples', ",", 'are', 'good', 'in', 'flavour']
        List after dropping punctuations and stopwords.
        List of words: ['red', 'apples', *, *, good, *, 'flavour']
        List of phrases: [('red', 'apples'), ('good',), ('flavour',)]

        List of phrases with a correct length:
        For the range [1, 2]: [('red', 'apples'), ('good',), ('flavour',)]
        For the range [1, 1]: [('good',), ('flavour',)]
        For the range [2, 2]: [('red', 'apples')]

        :param word_list: List of words which form a sentence when joined in
                          the same order.
        :return: List of contender phrases that are formed after dropping
                 stopwords and punctuations.
        """
        groups = groupby(word_list, lambda x: self._confirm_word_validity(x))
        phrases = [tuple(group[1]) for group in groups if group[0]]
        return list(
            filter(
                lambda x: self.min_length <= len(x) <= self.max_length, phrases
            )
        )
