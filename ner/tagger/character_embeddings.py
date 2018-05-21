import dynet as dy


class CharacterNetwork(object):

    def __init__(self, character_embeddings_size, encodings, rnn_size=100, rnn_layers=1, embeddings_size=100,
                 model=None):
        if model is None:
            self.model = dy.Model()
        else:
            self.model = model

        self.encodings = encodings

        self.character_embeddings_size = character_embeddings_size
        self.embeddings_size = embeddings_size
        self.num_characters = len(encodings.char2int)
        self.character_lookup = self.model.add_lookup_parameters((self.num_characters, character_embeddings_size))

        self.rnn_fw = []
        self.rnn_bw = []
        self.rnn_layers = rnn_layers
        self.rnn_size = rnn_size
        input_size = character_embeddings_size + 3

        for _ in range(rnn_layers):
            self.rnn_fw.append(dy.LSTMBuilder(1, input_size, rnn_size, self.model))
            self.rnn_bw.append(dy.LSTMBuilder(1, input_size, rnn_size, self.model))
            input_size = rnn_size * 2
        self.linearW = self.model.add_parameters(
            (embeddings_size, rnn_size * 4))  # last state and attention over the other states
        self.linearB = self.model.add_parameters((embeddings_size))

        self.att_w1 = self.model.add_parameters((rnn_size, rnn_size * 2))
        self.att_w2 = self.model.add_parameters((rnn_size, rnn_size * 2))
        self.att_v = self.model.add_parameters((1, rnn_size))

    def compute_embeddings(self, word, runtime=True):
        x_list = []
        uniword = unicode(word, 'utf-8')
        for i in range(len(uniword)):
            char = uniword[i]
            if char.lower() == char and char.upper() == char:
                style_emb = dy.inputVector([1.0, 0.0, 0.0])  # does not support uppercase
            elif char.lower() == char:
                style_emb = dy.inputVector([0.0, 1.0, 0.0])  # is lowercased
            else:
                style_emb = dy.inputVector([0.0, 0.0, 1.0])  # is uppercased

            char = char.lower()
            if char in self.encodings.char2int:
                x_list.append(dy.concatenate([self.character_lookup[self.encodings.char2int[char]], style_emb]))
            else:
                x_list.append(dy.concatenate([self.character_lookup[self.encodings.char2int['<UNK>']], style_emb]))

        rnn_outputs = x_list
        rnn_states_fw = None
        rnn_states_bw = None
        for rnn_fw, rnn_bw in zip(self.rnn_fw, self.rnn_bw):
            fw = []
            bw = []
            if runtime:
                rnn_fw.set_dropouts(0, 0)
                rnn_bw.set_dropouts(0, 0)
            else:
                rnn_fw.set_dropouts(0, 0.33)
                rnn_bw.set_dropouts(0, 0.33)

            rnn_fw = rnn_fw.initial_state()
            rnn_bw = rnn_bw.initial_state()
            rnn_states_fw = []
            rnn_states_bw = []
            for x in rnn_outputs:
                rnn_states_fw.append(rnn_fw.add_input(x))
                fw.append(rnn_states_fw[-1].output())
            for x in reversed(rnn_outputs):
                rnn_states_bw.append(rnn_bw.add_input(x))
                bw.append(rnn_states_bw[-1].output())
            rnn_outputs = []
            for x1, x2 in zip(fw, reversed(bw)):
                rnn_outputs.append(dy.concatenate([x1, x2]))

        attention = self._attend(rnn_outputs, rnn_states_fw[-1], rnn_states_bw[-1])

        pre_linear = dy.concatenate([fw[-1], bw[-1], attention])
        embedding = dy.tanh(self.linearW.expr() * pre_linear + self.linearB.expr())

        return embedding, rnn_outputs

    def _attend(self, input_vectors, state_fw, state_bw):
        w1 = self.att_w1.expr()
        w2 = self.att_w2.expr()
        v = self.att_v.expr()
        attention_weights = []

        w2dt = w2 * dy.concatenate([state_fw.h()[-1], state_bw.h()[-1]])
        for input_vector in input_vectors:
            attention_weight = v * dy.tanh(w1 * input_vector + w2dt)
            attention_weights.append(attention_weight)

        attention_weights = dy.softmax(dy.concatenate(attention_weights))

        output_vectors = dy.esum(
            [vector * attention_weight for vector, attention_weight in zip(input_vectors, attention_weights)])

        return output_vectors

