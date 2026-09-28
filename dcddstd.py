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

class DcddStd(Peer):
    def post_init(self):
        self.optimistic_peer = None
    
    def requests(self, peers, history):
        needed_pieces = []

        # Find all pieces I still need
        for i in range(len(self.pieces)):
            if self.pieces[i] < self.conf.blocks_per_piece:
                needed_pieces.append(i)

        # Count how many peers have each needed piece
        rarity = {}

        for piece_id in needed_pieces:
            count = 0

            for peer in peers:
                if piece_id in peer.available_pieces:
                    count += 1

            rarity[piece_id] = count

        requests = []

        # Go through each peer and decide what to ask them for
        for peer in peers:
            candidates = []

            # Find pieces I need that this peer has
            for piece_id in needed_pieces:
                if piece_id in peer.available_pieces:
                    candidates.append(piece_id)

            # Randomize ties
            random.shuffle(candidates)

            # Put rarest pieces first
            candidates.sort(key=lambda piece_id: rarity[piece_id])

            # Request at most max_requests pieces
            num_requests = min(self.max_requests, len(candidates))

            for i in range(num_requests):
                piece_id = candidates[i]
                start_block = self.pieces[piece_id]

                request = Request(
                    self.id,
                    peer.id,
                    piece_id,
                    start_block
                )

                requests.append(request)

        return requests

    def uploads(self, requests, peers, history):
        round_num = history.current_round()

        # If nobody is requesting from me, upload to nobody
        if len(requests) == 0:
            return []

        # Get unique IDs of peers currently requesting from me
        requester_ids = []
        for request in requests:
            if request.requester_id not in requester_ids:
                requester_ids.append(request.requester_id)

        # -----------------------------------
        # 1. REGULAR UNBLOCKING
        # -----------------------------------

        # Count how many blocks each requester gave me
        # during the previous two rounds
        recent_downloads = {}

        for peer_id in requester_ids:
            recent_downloads[peer_id] = 0

        # Look at at most the last two completed rounds
        recent_rounds = history.downloads[-2:]

        for round_downloads in recent_rounds:
            for download in round_downloads:
                if download.from_id in recent_downloads:
                    recent_downloads[download.from_id] += download.blocks

        # Randomize first so ties are broken randomly
        random.shuffle(requester_ids)

        # Sort by how much each peer recently uploaded to me
        requester_ids.sort(
            key=lambda peer_id: recent_downloads[peer_id],
            reverse=True
        )

        # Choose up to 3 peers with positive recent contribution
        regular_peers = []

        for peer_id in requester_ids:
            if recent_downloads[peer_id] > 0:
                regular_peers.append(peer_id)

            if len(regular_peers) == 3:
                break

        # -----------------------------------
        # 2. OPTIMISTIC UNBLOCKING
        # -----------------------------------

        # Peers eligible for optimistic unblocking are requesting
        # peers who are not already regularly unblocked
        optimistic_candidates = []

        for peer_id in requester_ids:
            if peer_id not in regular_peers:
                optimistic_candidates.append(peer_id)

        # Pick a new optimistic peer every 3 rounds.
        # Also pick a new one if the old peer stopped requesting
        # or became a regular peer.
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

        # -----------------------------------
        # 3. ALLOCATE BANDWIDTH
        # -----------------------------------

        chosen = list(regular_peers)

        if (
            self.optimistic_peer is not None
            and self.optimistic_peer not in chosen
            and self.optimistic_peer in requester_ids
        ):
            chosen.append(self.optimistic_peer)

        if len(chosen) == 0:
            return []

        # Divide my upload bandwidth evenly among chosen peers
        bws = even_split(self.up_bw, len(chosen))

        uploads = []

        for peer_id, bw in zip(chosen, bws):
            uploads.append(
                Upload(self.id, peer_id, bw)
            )

        return uploads
