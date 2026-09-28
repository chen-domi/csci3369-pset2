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

class DcddTourney(Peer):

    def post_init(self):
        self.upload_estimates = {}
        self.download_estimates = {}
    
    def requests(self, peers, history):
        needed_pieces = []

        for i in range(len(self.pieces)):
            if self.pieces[i] < self.conf.blocks_per_piece:
                needed_pieces.append(i)

        # Count how rare each piece is
        rarity = {}

        for piece_id in needed_pieces:
            count = 0

            for peer in peers:
                if piece_id in peer.available_pieces:
                    count += 1

            rarity[piece_id] = count

        requests = []

        for peer in peers:
            candidates = []

            for piece_id in needed_pieces:
                if piece_id in peer.available_pieces:
                    candidates.append(piece_id)

            # Randomize equal-rarity pieces
            random.shuffle(candidates)

            # Rarest pieces first
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
        # -----------------------------------------
        # 1. Initialize estimates for new peers
        # -----------------------------------------

        for peer in peers:
            peer_id = peer.id

            if peer_id not in self.upload_estimates:
                self.upload_estimates[peer_id] = max(
                    1.0,
                    self.up_bw / 4.0
                )

                self.download_estimates[peer_id] = 1.0

        # -----------------------------------------
        # 2. Update estimates using previous round
        # -----------------------------------------

        if history.current_round() > 0:

            previous_downloads = history.downloads[-1]
            previous_uploads = history.uploads[-1]

            # How much did each peer give us?
            downloaded_from = {}

            for download in previous_downloads:
                peer_id = download.from_id

                if peer_id not in downloaded_from:
                    downloaded_from[peer_id] = 0

                downloaded_from[peer_id] += download.blocks

            # Update download estimates
            for peer_id in downloaded_from:
                self.download_estimates[peer_id] = (
                    downloaded_from[peer_id]
                )

            # See who we uploaded to last round
            for upload in previous_uploads:
                peer_id = upload.to_id

                if peer_id not in self.upload_estimates:
                    continue

                # They gave us something back
                if (
                    peer_id in downloaded_from
                    and downloaded_from[peer_id] > 0
                ):
                    # They're a useful trading partner,
                    # so slightly lower our estimate of
                    # how much bandwidth they need.
                    self.upload_estimates[peer_id] *= 0.9

                    self.upload_estimates[peer_id] = max(
                        1.0,
                        self.upload_estimates[peer_id]
                    )

                else:
                    # We gave them bandwidth and got
                    # nothing back, so make them more
                    # expensive.
                    self.upload_estimates[peer_id] *= 1.2

        # -----------------------------------------
        # 3. Find unique peers requesting from us
        # -----------------------------------------

        requester_ids = []

        for request in requests:
            if request.requester_id not in requester_ids:
                requester_ids.append(
                    request.requester_id
                )

        if len(requester_ids) == 0:
            return []

        # -----------------------------------------
        # 4. Rank peers by value
        #
        # value = expected download / expected upload
        # -----------------------------------------

        random.shuffle(requester_ids)

        requester_ids.sort(
            key=lambda peer_id:
                self.download_estimates[peer_id]
                / self.upload_estimates[peer_id],
            reverse=True
        )

        # -----------------------------------------
        # 5. Reserve about 10% for exploration
        # -----------------------------------------

        optimistic_bw = int(
            round(self.up_bw * 0.10)
        )

        if self.up_bw > 1:
            optimistic_bw = max(
                1,
                optimistic_bw
            )

        optimistic_bw = min(
            optimistic_bw,
            self.up_bw
        )

        regular_bw = (
            self.up_bw - optimistic_bw
        )

        # -----------------------------------------
        # 6. Pick up to 3 best known peers
        # -----------------------------------------

        regular_peers = requester_ids[:3]

        # -----------------------------------------
        # 7. Split regular bandwidth based on score
        # -----------------------------------------

        allocations = {}

        if len(regular_peers) > 0:

            scores = {}
            total_score = 0.0

            for peer_id in regular_peers:

                score = (
                    self.download_estimates[peer_id]
                    / self.upload_estimates[peer_id]
                )

                scores[peer_id] = score
                total_score += score

            # Give bandwidth proportionally
            for peer_id in regular_peers:

                share = (
                    scores[peer_id]
                    / total_score
                )

                allocations[peer_id] = int(
                    share * regular_bw
                )

            # -----------------------------------------
            # Give out leftover bandwidth from rounding
            # -----------------------------------------

            used_bw = 0

            for peer_id in regular_peers:
                used_bw += allocations[peer_id]

            leftover = regular_bw - used_bw

            # Highest-ranked peers get leftovers first
            for i in range(leftover):
                peer_id = regular_peers[
                    i % len(regular_peers)
                ]

                allocations[peer_id] += 1

        # -----------------------------------------
        # 8. Pick an exploratory peer
        # -----------------------------------------

        optimistic_candidates = []

        for peer_id in requester_ids:
            if peer_id not in regular_peers:
                optimistic_candidates.append(
                    peer_id
                )

        if (
            optimistic_bw > 0
            and len(optimistic_candidates) > 0
        ):
            optimistic_peer = random.choice(
                optimistic_candidates
            )

            allocations[optimistic_peer] = (
                optimistic_bw
            )

        # If everybody is already a regular peer,
        # don't waste the optimistic bandwidth.
        elif (
            optimistic_bw > 0
            and len(regular_peers) > 0
        ):
            allocations[regular_peers[0]] += (
                optimistic_bw
            )

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
