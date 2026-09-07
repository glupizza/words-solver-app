RUSSIAN_ALPHABET = (
    "\u0430\u0431\u0432\u0433\u0434\u0435\u0451\u0436\u0437\u0438\u0439\u043a\u043b\u043c\u043d\u043e"
    "\u043f\u0440\u0441\u0442\u0443\u0444\u0445\u0446\u0447\u0448\u0449\u044a\u044b\u044c\u044d\u044e\u044f"
)
RUSSIAN_LETTER_BITS = {letter: 1 << index for index, letter in enumerate(RUSSIAN_ALPHABET)}


class TrieNode:
    def __init__(self):
        self.children = {}
        self.children_mask = 0
        self.is_end_of_word = False


class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word):
        node = self.root
        for char in word:
            child = node.children.get(char)
            if child is None:
                child = TrieNode()
                node.children[char] = child
                letter_bit = RUSSIAN_LETTER_BITS.get(char)
                if letter_bit is not None:
                    node.children_mask |= letter_bit
            node = child
        node.is_end_of_word = True

    def search(self, word):
        node = self.root
        for char in word:
            if char not in node.children:
                return False
            node = node.children[char]
        return node.is_end_of_word

    def starts_with(self, prefix):
        node = self.root
        for char in prefix:
            if char not in node.children:
                return False
            node = node.children[char]
        return True
