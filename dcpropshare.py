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

class DcPropShare(Peer):

    def post_init(self):
        pass

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
    # 2. Measure how much each requester contributed last round.
    # 3. Find which requesters actually contributed.
    # 4. If nobody contributed, give all bandwidth to a random requester.
    # 5. Reserve about 10% of bandwidth for optimistic uploading.
    # 6. Split the regular bandwidth proportionally among contributors.
    # 7. Give out any leftover bandwidth caused by rounding.
    # 8. Choose a peer for the optimistic bandwidth.
    # 9. Create and return the Upload objects.
    def uploads(self, requests, peers, history):

        if len(requests) == 0:
            return []

        # 1. Find the unique peers currently requesting from us.
        requester_ids = []

        for request in requests:
            if request.requester_id not in requester_ids:
                requester_ids.append(request.requester_id)

        # 2. Measure how much each requester contributed last round.
        contributions = {}

        for peer_id in requester_ids:
            contributions[peer_id] = 0

        if history.current_round() > 0:
            previous_downloads = history.downloads[-1]

            for download in previous_downloads:
                if download.from_id in contributions:
                    contributions[download.from_id] += download.blocks

        # 3. Find which requesters actually contributed.
        contributors = []

        for peer_id in requester_ids:
            if contributions[peer_id] > 0:
                contributors.append(peer_id)

        # 4. If nobody contributed, give all bandwidth to a random requester.
        if len(contributors) == 0:
            peer_id = random.choice(requester_ids)
            return [Upload(self.id, peer_id, self.up_bw)]

        # 5. Reserve about 10% of bandwidth for optimistic uploading.
        optimistic_bw = int(round(self.up_bw * 0.10))

        if self.up_bw > 1:
            optimistic_bw = max(1, optimistic_bw)

        optimistic_bw = min(optimistic_bw, self.up_bw)
        regular_bw = self.up_bw - optimistic_bw

        # 6. Split the regular bandwidth proportionally among contributors.
        total_contribution = 0

        for peer_id in contributors:
            total_contribution += contributions[peer_id]

        allocations = {}

        for peer_id in contributors:
            share = contributions[peer_id] / total_contribution
            allocations[peer_id] = int(share * regular_bw)

        # 7. Give out any leftover bandwidth caused by rounding.
        used_regular_bw = 0

        for peer_id in contributors:
            used_regular_bw += allocations[peer_id]

        leftover = regular_bw - used_regular_bw
        random.shuffle(contributors)

        for i in range(leftover):
            peer_id = contributors[i % len(contributors)]
            allocations[peer_id] += 1

        # 8. Choose a peer for the optimistic bandwidth.
        optimistic_candidates = []

        for peer_id in requester_ids:
            if peer_id not in contributors:
                optimistic_candidates.append(peer_id)

        if len(optimistic_candidates) > 0:
            optimistic_peer = random.choice(optimistic_candidates)
        else:
            optimistic_peer = random.choice(requester_ids)

        if optimistic_peer in allocations:
            allocations[optimistic_peer] += optimistic_bw
        else:
            allocations[optimistic_peer] = optimistic_bw

        # 9. Create and return the Upload objects.
        uploads = []

        for peer_id in allocations:
            bw = allocations[peer_id]

            if bw > 0:
                uploads.append(Upload(self.id, peer_id, bw))

        return uploads
