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

class DcddTyrant(Peer):

    def post_init(self):
        self.upload_estimates = {}
        self.download_estimates = {}
        self.recip_rounds = {}

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

    # 1. Initialize estimates for new peers.
    # 2. Update estimates using the previous round.
    # 3. Find the unique peers currently requesting from us.
    # 4. Keep only requesters that have pieces we still need.
    # 5. Rank those peers by d_j / u_j.
    # 6. Give bandwidth to the highest-value peers until capacity is full.
    def uploads(self, requests, peers, history):
        # 1. Initialize estimates for new peers.
        for peer in peers:
            peer_id = peer.id

            if peer_id not in self.upload_estimates:
                self.upload_estimates[peer_id] = max(1.0, self.up_bw / 4.0)
                self.download_estimates[peer_id] = 1.0
                self.recip_rounds[peer_id] = 0

        # 2. Update estimates using the previous round.
        if history.current_round() > 0:
            previous_downloads = history.downloads[-1]
            previous_uploads = history.uploads[-1]
            downloaded_from = {}

            for download in previous_downloads:
                peer_id = download.from_id

                if peer_id not in downloaded_from:
                    downloaded_from[peer_id] = 0

                downloaded_from[peer_id] += download.blocks

            for peer_id in downloaded_from:
                self.download_estimates[peer_id] = downloaded_from[peer_id]

            uploaded_to = []

            for upload in previous_uploads:
                uploaded_to.append(upload.to_id)

            for peer_id in uploaded_to:
                reciprocated = (
                    peer_id in downloaded_from
                    and downloaded_from[peer_id] > 0
                )

                if reciprocated:
                    self.recip_rounds[peer_id] += 1

                    if self.recip_rounds[peer_id] >= 3:
                        self.upload_estimates[peer_id] *= 0.9
                        self.upload_estimates[peer_id] = max(
                            1.0, self.upload_estimates[peer_id]
                        )
                        self.recip_rounds[peer_id] = 0

                else:
                    self.upload_estimates[peer_id] *= 1.2
                    self.recip_rounds[peer_id] = 0

        # 3. Find the unique peers currently requesting from us.
        requester_ids = []

        for request in requests:
            if request.requester_id not in requester_ids:
                requester_ids.append(request.requester_id)

        if len(requester_ids) == 0:
            return []

        # 4. Keep only requesters that have pieces we still need.
        needed_pieces = []

        for i in range(len(self.pieces)):
            if self.pieces[i] < self.conf.blocks_per_piece:
                needed_pieces.append(i)

        eligible = []

        for peer in peers:
            if peer.id not in requester_ids:
                continue

            useful = False

            for piece_id in needed_pieces:
                if piece_id in peer.available_pieces:
                    useful = True
                    break

            if useful:
                eligible.append(peer.id)

        if len(eligible) == 0:
            return []

        # 5. Rank those peers by d_j / u_j.
        random.shuffle(eligible)

        eligible.sort(
            key=lambda peer_id:
                self.download_estimates[peer_id] / self.upload_estimates[peer_id],
            reverse=True
        )

        # 6. Give bandwidth to the highest-value peers until capacity is full.
        uploads = []
        used_bandwidth = 0

        for peer_id in eligible:
            amount = max(1, int(round(self.upload_estimates[peer_id])))

            if used_bandwidth + amount <= self.up_bw:
                uploads.append(Upload(self.id, peer_id, amount))
                used_bandwidth += amount

        return uploads
