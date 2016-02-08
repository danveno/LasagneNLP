__author__ = 'max'

import numpy as np
from gensim.models.word2vec import Word2Vec
import theano

from alphabet import Alphabet
from lasagne_nlp.utils import utils as utils

root_symbol = "##ROOT##"
root_label = "<ROOT>"
MAX_LENGTH = 120
logger = utils.get_logger("LoadData")


def read_conll_sequence_labeling(path, word_alphabet, label_alphabet, word_column=1, label_column=4):
    """
    read data from file in conll format
    :param path: file path
    :param word_column: the column index of word (start from 0)
    :param label_column: the column of label (start from 0)
    :param word_alphabet: alphabet of words
    :param label_alphabet: alphabet -f labels
    :return: sentences of words and labels, sentences of indexes of words and labels.
    """

    word_sentences = []
    label_sentences = []

    word_index_sentences = []
    label_index_sentences = []

    words = []
    labels = []

    word_ids = []
    label_ids = []

    num_tokens = 0
    with open(path) as file:
        for line in file:
            if line.strip() == "":
                if 0 < len(words) <= MAX_LENGTH:
                    word_sentences.append(words[:])
                    label_sentences.append(labels[:])

                    word_index_sentences.append(word_ids[:])
                    label_index_sentences.append(label_ids[:])

                    num_tokens += len(words)
                else:
                    logger.info("ignore sentence with length %d" % (len(words)))

                words = []
                labels = []

                word_ids = []
                label_ids = []
            else:
                tokens = line.strip().split()
                word = tokens[word_column]
                label = tokens[label_column]

                words.append(word)
                labels.append(label)

                word_id = word_alphabet.get_index(word)
                label_id = label_alphabet.get_index(label)

                word_ids.append(word_id)
                label_ids.append(label_id)

    logger.info("#sentences: %d, #tokens: %d" % (len(word_sentences), num_tokens))
    return word_sentences, label_sentences, word_index_sentences, label_index_sentences


def load_dataset_sequence_labeling(train_path, dev_path, test_path, word_column=1, label_column=4,
                                   label_name='pos', oov='embedding', fine_tune=False, embedding="word2Vec",
                                   embedding_path="data/word2vec/GoogleNews-vectors-negative300.bin"):
    """
    load data from file
    :param train_path: path of training file
    :param dev_path: path of dev file
    :param test_path: path of test file
    :param word_column: the column index of word (start from 0)
    :param label_column: the column of label (start from 0)
    :param label_name: name of label, such as pos or ner
    :param oov: embedding for oov word, choose from ['random', 'embedding']. If "embedding", then add words in dev and
                test data to alphabet; if "random", not.
    :param fine_tune: if fine tune word embeddings.
    :param embedding: embeddings for words, choose from ['word2vec', 'senna'].
    :param embedding_path: path of file storing word embeddings.
    :return: X_train, Y_train, mask_train, X_dev, Y_dev, mask_dev, X_test, Y_test, mask_test,
            embedd_table (if fine tune), label_size
    """

    def get_max_length(word_sentences):
        max_length = 0
        for sentence in word_sentences:
            length = len(sentence)
            if length > max_length:
                max_length = length
        return max_length

    def construct_tensor_fine_tune(word_index_sentences, label_index_sentences, max_length):
        X = np.empty([len(word_index_sentences), max_length], dtype=np.int32)
        Y = np.empty([len(word_index_sentences), max_length], dtype=np.int32)
        mask = np.zeros([len(word_index_sentences), max_length], dtype=theano.config.floatX)

        for i in range(len(word_index_sentences)):
            word_ids = word_index_sentences[i]
            label_ids = label_index_sentences[i]
            length = len(word_ids)
            for j in range(length):
                wid = word_ids[j]
                label = label_ids[j]
                X[i, j] = wid
                Y[i, j] = label - 1

            # Zero out X after the end of the sequence
            X[i, length:] = 0
            # Copy the last label after the end of the sequence
            Y[i, length:] = Y[i, length - 1]
            # Make the mask for this sample 1 within the range of length
            mask[i, :length] = 1
        return X, Y, mask

    def build_embedd_table(word_alphabet, embedd_dict, embedd_dim):
        scale = np.sqrt(3.0 / embedd_dim)
        embedd_table = np.empty([word_alphabet.size(), embedd_dim], dtype=theano.config.floatX)
        embedd_table[word_alphabet.default_index, :] = np.random.uniform(-scale, scale, [1, embedd_dim])
        for word, index in word_alphabet.iteritems():
            embedd = embedd_dict[word] if word in embedd_dict else np.random.uniform(-scale, scale, [1, embedd_dim])
            embedd_table[index, :] = embedd
        return embedd_table

    def generate_dataset_fine_tune(word_index_sentences_train, label_index_sentences_train,
                                   word_index_sentences_dev, label_index_sentences_dev,
                                   word_index_sentences_test, label_index_sentences_test,
                                   word_alphabet, embedding, embedding_path):
        """
        generate data tensor when fine tuning
        :param word_index_sentences_train: word index in training data
        :param label_index_sentences_train: training target label indexes
        :param word_index_sentences_dev: word index in dev data
        :param label_index_sentences_dev: dev target label indexes
        :param word_index_sentences_test: word index in test data
        :param label_index_sentences_test: test target label indexes
        :param word_alphabet: alphabet of words
        :param embedding: embedding: embeddings for words, choose from ['word2vec', 'senna'].
        :param embedding_path: embedding_path: path of file storing word embeddings.
        :return: X_train, Y_train, mask_train, X_dev, Y_dev, mask_dev, X_test, Y_test, mask_test, embedd_table, label_size
        """

        # get maximum length
        max_length_train = get_max_length(word_sentences_train)
        max_length_dev = get_max_length(word_sentences_dev)
        max_length_test = get_max_length(word_sentences_test)
        max_length = min(MAX_LENGTH, max(max_length_train, max_length_dev, max_length_test))
        logger.info("Maximum length of training set is %d" % (max_length_train))
        logger.info("Maximum length of dev set is %d" % (max_length_dev))
        logger.info("Maximum length of test set is %d" % (max_length_test))
        logger.info("Maximum length used for training is %d" % (max_length))

        if embedding == 'word2vec':
            # loading word2vec
            logger.info("Loading word2vec ...")
            word2vec = Word2Vec.load_word2vec_format(embedding_path, binary=True)
            embedd_dim = word2vec.vector_size
            logger.info("Dimension of embedding is %d" % (embedd_dim))

            # fill data tensor (X.shape = [#data, max_length], Y.shape = [#data, max_length])
            X_train, Y_train, mask_train = construct_tensor_fine_tune(word_index_sentences_train,
                                                                      label_index_sentences_train, max_length)
            X_dev, Y_dev, mask_dev = construct_tensor_fine_tune(word_index_sentences_dev, label_index_sentences_dev,
                                                                max_length)
            X_test, Y_test, mask_test = construct_tensor_fine_tune(word_index_sentences_test,
                                                                   label_index_sentences_test, max_length)
            return X_train, Y_train, mask_train, X_dev, Y_dev, mask_dev, X_test, Y_test, mask_test, \
                   build_embedd_table(word_alphabet, word2vec, embedd_dim), label_alphabet.size() - 1
        elif embedding == 'senna':
            return None
        else:
            raise ValueError("embedding should choose from [word2vec, senna]")

    def construct_tensor_not_fine_tune(word_sentences, label_index_sentences, unknown_embedd, embedd_dict, max_length,
                                       embedd_dim):
        X = np.empty([len(word_sentences), max_length, embedd_dim], dtype=theano.config.floatX)
        Y = np.empty([len(word_sentences), max_length], dtype=np.int32)
        mask = np.zeros([len(word_sentences), max_length], dtype=theano.config.floatX)
        for i in range(len(word_sentences)):
            words = word_sentences[i]
            label_ids = label_index_sentences[i]
            length = len(words)
            for j in range(length):
                word = words[j]
                label = label_ids[j]
                embedd = embedd_dict[word] if word in embedd_dict else unknown_embedd
                X[i, j, :] = embedd
                Y[i, j] = label - 1

            # Zero out X after the end of the sequence
            X[i, length:] = np.zeros([1, embedd_dim], dtype=theano.config.floatX)
            # Copy the last label after the end of the sequence
            Y[i, length:] = Y[i, length - 1]
            # Make the mask for this sample 1 within the range of length
            mask[i, :length] = 1
        return X, Y, mask

    def generate_dataset_not_fine_tune(word_sentences_train, label_index_sentences_train, word_sentences_dev,
                                       label_index_sentences_dev, word_sentences_test, label_index_sentences_test,
                                       embedding, embedding_path):
        """
        generate data tensor when not fine tuning
        :param word_sentences_train: training data
        :param label_index_sentences_train: training target label indexes
        :param word_sentences_dev: dev data
        :param label_index_sentences_dev: dev target label indexes
        :param word_sentences_test: test data
        :param label_index_sentences_test: test target label indexes
        :param embedding: embeddings for words, choose from ['word2vec', 'senna'].
        :param embedding_path: path of file storing word embeddings.
        :return: X_train, Y_train, mask_train, X_dev, Y_dev, mask_dev, X_test, Y_test, mask_test, None, label_size
        """

        # get maximum length
        max_length_train = get_max_length(word_sentences_train)
        max_length_dev = get_max_length(word_sentences_dev)
        max_length_test = get_max_length(word_sentences_test)
        max_length = min(MAX_LENGTH, max(max_length_train, max_length_dev, max_length_test))
        logger.info("Maximum length of training set is %d" % (max_length_train))
        logger.info("Maximum length of dev set is %d" % (max_length_dev))
        logger.info("Maximum length of test set is %d" % (max_length_test))
        logger.info("Maximum length used for training is %d" % (max_length))

        if embedding == 'word2vec':
            # loading word2vec
            logger.info("Loading word2vec ...")
            word2vec = Word2Vec.load_word2vec_format(embedding_path, binary=True)
            embedd_dim = word2vec.vector_size
            logger.info("Dimension of embedding is %d" % (embedd_dim))

            # fill data tensor (X.shape = [#data, max_length, embedding_dim], Y.shape = [#data, max_length])
            unknown_embedd = np.random.uniform(-0.01, 0.01, [1, embedd_dim])
            X_train, Y_train, mask_train = construct_tensor_not_fine_tune(word_sentences_train,
                                                                          label_index_sentences_train, unknown_embedd,
                                                                          word2vec, max_length, embedd_dim)
            X_dev, Y_dev, mask_dev = construct_tensor_not_fine_tune(word_sentences_dev, label_index_sentences_dev,
                                                                    unknown_embedd, word2vec, max_length, embedd_dim)
            X_test, Y_test, mask_test = construct_tensor_not_fine_tune(word_sentences_test, label_index_sentences_test,
                                                                       unknown_embedd, word2vec, max_length, embedd_dim)
            return X_train, Y_train, mask_train, X_dev, Y_dev, mask_dev, X_test, Y_test, mask_test, \
                   None, label_alphabet.size() - 1
        elif embedding == 'senna':
            return None
        else:
            raise ValueError("embedding should choose from [word2vec, senna]")

    word_alphabet = Alphabet('word')
    label_alphabet = Alphabet(label_name)

    # read training data
    logger.info("Reading data from training set...")
    word_sentences_train, _, word_index_sentences_train, label_index_sentences_train = read_conll_sequence_labeling(
        train_path, word_alphabet, label_alphabet, word_column, label_column)

    # if oov is "random" and do not fine tune, close word_alphabet
    if oov == "random" and not fine_tune:
        logger.info("Close word alphabet.")
        word_alphabet.close()

    # read dev data
    logger.info("Reading data from dev set...")
    word_sentences_dev, _, word_index_sentences_dev, label_index_sentences_dev = read_conll_sequence_labeling(
        dev_path, word_alphabet, label_alphabet, word_column, label_column)

    # read test data
    logger.info("Reading data from test set...")
    word_sentences_test, _, word_index_sentences_test, label_index_sentences_test = read_conll_sequence_labeling(
        test_path, word_alphabet, label_alphabet, word_column, label_column)

    logger.info("word alphabet size: %d" % (word_alphabet.size() - 1))
    logger.info("label alphabet size: %d" % (label_alphabet.size() - 1))

    if fine_tune:
        logger.info("Generating data with fine tuning...")
        return generate_dataset_fine_tune(word_index_sentences_train, label_index_sentences_train,
                                          word_index_sentences_dev, label_index_sentences_dev,
                                          word_index_sentences_test, label_index_sentences_test,
                                          word_alphabet, embedding, embedding_path)
    else:
        logger.info("Generating data without fine tuning...")
        return generate_dataset_not_fine_tune(word_sentences_train, label_index_sentences_train,
                                              word_sentences_dev, label_index_sentences_dev,
                                              word_sentences_test, label_index_sentences_test,
                                              embedding, embedding_path)