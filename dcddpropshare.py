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

class DcddPropShare(Peer):

    def post_init(self):
        pass

    def requests(self, peers, history):
        # Find all pieces I still need
        needed_pieces = []

        for i in range(len(self.pieces)):
            if self.pieces[i] < self.conf.blocks_per_piece:
                needed_pieces.append(i)

        # Count rarity of each needed piece
        rarity = {}

        for piece_id in needed_pieces:
            count = 0

            for peer in peers:
                if piece_id in peer.available_pieces:
                    count += 1

            rarity[piece_id] = count

        requests = []

        # Consider each peer independently
        for peer in peers:
            candidates = []

            # Pieces I need that this peer has
            for piece_id in needed_pieces:
                if piece_id in peer.available_pieces:
                    candidates.append(piece_id)

            # Randomize ties
            random.shuffle(candidates)

            # Then sort rarest-first
            candidates.sort(
                key=lambda piece_id: rarity[piece_id]
            )

            num_requests = min(
                self.max_requests,
                len(candidates)
            )

            for i in range(num_requests):
                piece_id = candidates[i]

                request = Request(
                    self.id,
                    peer.id,
                    piece_id,
                    self.pieces[piece_id]
                )

                requests.append(request)

        return requests

    def uploads(self, requests, peers, history):

        # If nobody is requesting from us, upload to nobody
        if len(requests) == 0:
            return []

        # -----------------------------------------
        # 1. Find unique peers requesting from us
        # -----------------------------------------

        requester_ids = []

        for request in requests:
            if request.requester_id not in requester_ids:
                requester_ids.append(request.requester_id)

        # -----------------------------------------
        # 2. Look at downloads from previous round
        # -----------------------------------------

        contributions = {}

        for peer_id in requester_ids:
            contributions[peer_id] = 0

        round_num = history.current_round()

        if round_num > 0:
            previous_downloads = history.downloads[-1]
            for download in previous_downloads:
                # Only count peers who are requesting from us now
                if download.from_id in contributions:
                    contributions[download.from_id] += download.blocks

        # -----------------------------------------
        # 3. Find peers who contributed last round
        # -----------------------------------------

        contributors = []

        for peer_id in requester_ids:
            if contributions[peer_id] > 0:
                contributors.append(peer_id)

        # -----------------------------------------
        # 4. If nobody contributed last round,
        #    use all bandwidth optimistically
        # -----------------------------------------

        if len(contributors) == 0:
            peer_id = random.choice(requester_ids)

            return [
                Upload(
                    self.id,
                    peer_id,
                    self.up_bw
                )
            ]

        # -----------------------------------------
        # 5. Reserve about 10% for optimistic upload
        # -----------------------------------------

        optimistic_bw = int(round(self.up_bw * 0.10))

        # Make sure there is at least 1 block
        # for optimistic unblocking when possible
        if self.up_bw > 1:
            optimistic_bw = max(1, optimistic_bw)

        optimistic_bw = min(
            optimistic_bw,
            self.up_bw
        )

        regular_bw = self.up_bw - optimistic_bw

        # -----------------------------------------
        # 6. Split regular bandwidth proportionally
        # -----------------------------------------

        total_contribution = 0

        for peer_id in contributors:
            total_contribution += contributions[peer_id]

        allocations = {}

        for peer_id in contributors:

            share = (
                contributions[peer_id]
                / total_contribution
            )

            # Start by rounding down
            allocations[peer_id] = int(
                share * regular_bw
            )

        # -----------------------------------------
        # 7. Give leftover blocks caused by rounding
        # -----------------------------------------

        used_regular_bw = 0

        for peer_id in contributors:
            used_regular_bw += allocations[peer_id]

        leftover = regular_bw - used_regular_bw

        # Randomize who gets rounding leftovers
        random.shuffle(contributors)

        for i in range(leftover):
            peer_id = contributors[i % len(contributors)]
            allocations[peer_id] += 1

        # -----------------------------------------
        # 8. Choose optimistic peer
        # -----------------------------------------

        optimistic_candidates = []

        # Prefer someone who did NOT contribute last round
        for peer_id in requester_ids:
            if peer_id not in contributors:
                optimistic_candidates.append(peer_id)

        if len(optimistic_candidates) > 0:
            optimistic_peer = random.choice(
                optimistic_candidates
            )
        else:
            # Everyone contributed, so pick any requester
            optimistic_peer = random.choice(
                requester_ids
            )

        # Add optimistic bandwidth
        if optimistic_peer in allocations:
            allocations[optimistic_peer] += optimistic_bw
        else:
            allocations[optimistic_peer] = optimistic_bw

        # -----------------------------------------
        # 9. Create Upload objects
        # -----------------------------------------

        uploads = []

        for peer_id in allocations:
            bw = allocations[peer_id]
            if bw > 0:
                uploads.append(
                    Upload(
                        self.id,
                        peer_id,
                        bw
                    )
                )

        return uploads
