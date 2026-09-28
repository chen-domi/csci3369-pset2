import random

from messages import Upload, Request
from util import even_split
from peer import Peer


class DcddStd(Peer):

    def requests(self, peers, history):
        needed = {
            i for i in range(len(self.pieces))
            if self.pieces[i] < self.conf.blocks_per_piece
        }

        rarity = {
            i: sum(i in peer.available_pieces for peer in peers)
            for i in needed
        }

        requests = []

        for peer in peers:
            choices = [i for i in peer.available_pieces if i in needed]

            # randomize ties, then put rarest pieces first
            random.shuffle(choices)
            choices.sort(key=lambda i: rarity[i])

            for piece_id in choices[:self.max_requests]:
                requests.append(
                    Request(self.id, peer.id, piece_id, self.pieces[piece_id])
                )


