#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers 
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer

#!/usr/bin/python

class DcStd(Peer):

    def post_init(self):
        self.optimistic_peer = None

    # 1. Find the pieces we still need.
    # 2. Count how rare each needed piece is.
    # 3. For each peer, find which needed pieces they have.
    # 4. Randomize ties and put rarest pieces first.
    # 5. Request up to max_requests pieces from each peer.
    def requests(self, peers, history):
        # 1. Find the pieces we still need.
        needed_pieces = []

        for i in range(len(self.pieces)):
            if self.pieces[i] < self.conf.blocks_per_piece:
                needed_pieces.append(i)

        # 2. Count how rare each needed piece is.
        rarity = {}

        for piece_id in needed_pieces:
            count = 0

            for peer in peers:
                if piece_id in peer.available_pieces:
                    count += 1

            rarity[piece_id] = count

        requests = []

        # 3. For each peer, find which needed pieces they have.
        for peer in peers:
            candidates = []

            for piece_id in needed_pieces:
                if piece_id in peer.available_pieces:
                    candidates.append(piece_id)

            # 4. Randomize ties and put rarest pieces first.
            random.shuffle(candidates)
            candidates.sort(key=lambda piece_id: rarity[piece_id])

            # 5. Request up to max_requests pieces from each peer.
            num_requests = min(self.max_requests, len(candidates))

            for i in range(num_requests):
                piece_id = candidates[i]
                requests.append(
                    Request(self.id, peer.id, piece_id, self.pieces[piece_id])
                )

        return requests

    # 1. Find the unique peers currently requesting from us.
    # 2. Measure how much each requester gave us in the last two rounds.
    # 3. Choose up to 3 regular peers with the highest contributions.
    # 4. Choose an optimistic peer from the remaining requesters.
    # 5. Combine the regular and optimistic peers.
    # 6. Split upload bandwidth evenly and return the Upload objects.
    def uploads(self, requests, peers, history):
        round_num = history.current_round()

        if len(requests) == 0:
            return []

        # 1. Find the unique peers currently requesting from us.
        requester_ids = []

        for request in requests:
            if request.requester_id not in requester_ids:
                requester_ids.append(request.requester_id)

        # 2. Measure how much each requester gave us in the last two rounds.
        recent_downloads = {}

        for peer_id in requester_ids:
            recent_downloads[peer_id] = 0

        recent_rounds = history.downloads[-2:]

        for round_downloads in recent_rounds:
            for download in round_downloads:
                if download.from_id in recent_downloads:
                    recent_downloads[download.from_id] += download.blocks

        # 3. Choose up to 3 regular peers with the highest contributions.
        random.shuffle(requester_ids)

        requester_ids.sort(
            key=lambda peer_id: recent_downloads[peer_id],
            reverse=True
        )

        regular_peers = []

        for peer_id in requester_ids:
            if recent_downloads[peer_id] > 0:
                regular_peers.append(peer_id)

            if len(regular_peers) == 3:
                break

        # 4. Choose an optimistic peer from the remaining requesters.
        optimistic_candidates = []

        for peer_id in requester_ids:
            if peer_id not in regular_peers:
                optimistic_candidates.append(peer_id)

        choose_new_optimistic = (
            round_num % 3 == 0
            or self.optimistic_peer not in requester_ids
            or self.optimistic_peer in regular_peers
        )

        if choose_new_optimistic:
            if len(optimistic_candidates) > 0:
                self.optimistic_peer = random.choice(optimistic_candidates)
            else:
                self.optimistic_peer = None

        # 5. Combine the regular and optimistic peers.
        chosen = list(regular_peers)

        if (
            self.optimistic_peer is not None
            and self.optimistic_peer not in chosen
            and self.optimistic_peer in requester_ids
        ):
            chosen.append(self.optimistic_peer)

        if len(chosen) == 0:
            return []

        # 6. Split upload bandwidth evenly and return the Upload objects.
        bws = even_split(self.up_bw, len(chosen))
        uploads = []

        for peer_id, bw in zip(chosen, bws):
            uploads.append(Upload(self.id, peer_id, bw))

        return uploads
