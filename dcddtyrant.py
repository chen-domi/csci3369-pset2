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
        # u_j:
        # estimated amount we need to upload to peer j
        # in order to get that peer to reciprocate
        self.upload_estimates = {}

        # d_j:
        # estimated amount we expect to download from peer j
        self.download_estimates = {}

        # Number of consecutive successful reciprocation rounds
        self.recip_rounds = {}

    def requests(self, peers, history):
        # Find pieces that we still need
        needed_pieces = []

        for i in range(len(self.pieces)):
            if self.pieces[i] < self.conf.blocks_per_piece:
                needed_pieces.append(i)

        # Count how many peers have each piece
        rarity = {}

        for piece_id in needed_pieces:
            count = 0

            for peer in peers:
                if piece_id in peer.available_pieces:
                    count += 1

            rarity[piece_id] = count

        requests = []

        # Request pieces from each peer
        for peer in peers:
            candidates = []

            # Pieces I need that this peer has
            for piece_id in needed_pieces:
                if piece_id in peer.available_pieces:
                    candidates.append(piece_id)

            # Randomize equal-rarity pieces
            random.shuffle(candidates)

            # Prefer rare pieces
            candidates.sort(
                key=lambda piece_id: rarity[piece_id]
            )

            num_requests = min(
                self.max_requests,
                len(candidates)
            )

            for i in range(num_requests):
                piece_id = candidates[i]

                # Start from the next block we need
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
        # -----------------------------------------
        # 1. Initialize estimates for new peers
        # -----------------------------------------

        for peer in peers:
            peer_id = peer.id

            if peer_id not in self.upload_estimates:
                # Initial guess for u_j.
                # Roughly one normal BitTorrent upload slot.
                self.upload_estimates[peer_id] = max(
                    1.0,
                    self.up_bw / 4.0
                )

                # Initial d_j estimate.
                self.download_estimates[peer_id] = 1.0

                self.recip_rounds[peer_id] = 0

        # -----------------------------------------
        # 2. Use previous round to update estimates
        # -----------------------------------------

        if history.current_round() > 0:

            previous_downloads = history.downloads[-1]
            previous_uploads = history.uploads[-1]

            # How many blocks did each peer give me?
            downloaded_from = {}

            for download in previous_downloads:
                peer_id = download.from_id

                if peer_id not in downloaded_from:
                    downloaded_from[peer_id] = 0

                downloaded_from[peer_id] += download.blocks

            # If we actually downloaded from a peer,
            # update d_j using the observed amount.
            for peer_id in downloaded_from:
                self.download_estimates[peer_id] = downloaded_from[peer_id]

            # Determine who we uploaded to last round
            uploaded_to = []

            for upload in previous_uploads:
                uploaded_to.append(upload.to_id)

            # Update u_j depending on whether they reciprocated
            for peer_id in uploaded_to:

                reciprocated = (
                    peer_id in downloaded_from
                    and downloaded_from[peer_id] > 0
                )

                if reciprocated:
                    self.recip_rounds[peer_id] += 1

                    # After 3 successful rounds,
                    # try lowering our bid by 10%
                    if self.recip_rounds[peer_id] >= 3:
                        self.upload_estimates[peer_id] *= 0.9

                        # Never let the estimate fall below 1 block
                        self.upload_estimates[peer_id] = max(
                            1.0,
                            self.upload_estimates[peer_id]
                        )

                        self.recip_rounds[peer_id] = 0

                else:
                    # They didn't reciprocate, so raise our bid by 20%
                    self.upload_estimates[peer_id] *= 1.2
                    self.recip_rounds[peer_id] = 0

        # -----------------------------------------
        # 3. Find peers currently requesting from us
        # -----------------------------------------

        requester_ids = []

        for request in requests:
            if request.requester_id not in requester_ids:
                requester_ids.append(request.requester_id)

        if len(requester_ids) == 0:
            return []

        # -----------------------------------------
        # 4. Only consider peers that have pieces
        #    that we still need
        # -----------------------------------------

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

        # -----------------------------------------
        # 5. Rank peers by d_j / u_j
        # -----------------------------------------

        random.shuffle(eligible)

        eligible.sort(
            key=lambda peer_id:
                self.download_estimates[peer_id]
                / self.upload_estimates[peer_id],
            reverse=True
        )

        # -----------------------------------------
        # 6. Give bandwidth to highest-value peers
        #    until our upload capacity is exhausted
        # -----------------------------------------

        uploads = []
        used_bandwidth = 0

        for peer_id in eligible:

            amount = max(
                1,
                int(round(self.upload_estimates[peer_id]))
            )

            if used_bandwidth + amount <= self.up_bw:

                uploads.append(
                    Upload(
                        self.id,
                        peer_id,
                        amount
                    )
                )

                used_bandwidth += amount

        return uploads
