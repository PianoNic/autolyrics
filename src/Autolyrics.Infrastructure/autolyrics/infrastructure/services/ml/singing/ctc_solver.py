from dataclasses import dataclass, field

import numpy as np

from autolyrics.infrastructure.services.ml.singing.acoustic import Emissions


@dataclass
class SolverLine:
    words: list[list[int]]  # token ids per word; empty for a word with nothing to align
    prior_start: float | None = None  # seconds: where the source says the line starts
    prior_end: float | None = None  # seconds: where the source says it is over (next line)
    # Words from this index on are optional and skipped together: background vocals sung after
    # the line ("Warum?", "Och, nö!"), placed here when the audio has them between the lines.
    optional_from: int | None = None


@dataclass
class TokenSpan:
    begin: int  # first frame
    end: int  # one past the last frame
    score: float  # mean probability over its frames


@dataclass
class WordSpan:
    line: int
    word: int
    begin: float
    end: float
    score: float
    tokens: list[TokenSpan] = field(default_factory=list)


@dataclass
class _Label:
    token: int
    optional: bool
    line: int = -1
    word: int = -1
    first_of_line: bool = False
    group: int = -1  # optional block the label belongs to (skipped as a whole)


class GlobalCtcSolver:
    """CTC Viterbi over the whole song at once.

    Every word is placed in one pass, so lines cannot overtake or push each other the way
    window-by-window alignment lets them. Where a lyrics source gave line times, they are a soft
    pull on each line's first token, never a window: a line may move as far as the audio says,
    it just costs more the further it strays. Gap tokens between words and lines are optional,
    so connected singing does not need a pause and ad-libs have somewhere to go.
    """

    NEG = -1e30
    GAP_LOGP = -1.5  # per frame for a line gap that soaks up sound the lyrics do not cover
    TRIM = 0.3  # a token ends at its last frame heard at least this share of its peak

    def __init__(self, prior_weight: float = 3.0, prior_tolerance: float = 0.35,
                 window_weight: float = 2.0, window_tolerance: float = 1.0,
                 filler: float | None = None, inner_blank: float = 0.1,
                 together: float = 0.0):
        # Nats per frame of silence between the words of one line: for short exclamations
        # ("Och, nö!") that are said in one breath.
        self._together = together
        # Nats per frame of silence between two sounds of the same word: a word is sung in one
        # go, so its last sound cannot wander off to a similar sound seconds later.
        self._inner_blank = inner_blank
        self._filler = filler  # nats per frame a filler pays below the best-matching token
        self._weight = prior_weight  # nats per second beyond the tolerance, on a line's start
        self._tolerance = prior_tolerance
        # Every token of a line pays this per second it sits outside the line's source span:
        # weak acoustic evidence (whispers, effects) can no longer squeeze lines elsewhere.
        self._window_weight = window_weight
        self._window_tolerance = window_tolerance

    def solve(self, em: Emissions, lines: list[SolverLine], word_gap: int | None,
              line_gap: int | None, prior_offset: float = 0.0) -> list[WordSpan]:
        labels = self._labels(lines, word_gap, line_gap)
        if not labels:
            return []
        logp = em.logp
        if line_gap is not None:
            logp = logp.copy()
            logp[:, line_gap] = self.GAP_LOGP
        elif self._filler is not None:
            # A model without a garbage token gets one: an optional filler between lines that
            # matches whatever is sung, at a cost. Ad-libs and background words that are not
            # in the line then land in it instead of stretching the line's last word.
            sung = np.delete(logp, em.blank, axis=1).max(axis=1, keepdims=True)
            logp = np.concatenate((logp, sung - self._filler), axis=1)
            line_gap = logp.shape[1] - 1
            labels = self._labels(lines, word_gap, line_gap)
        path = self._viterbi(logp, em, labels, lines, prior_offset)
        # How well the audio supports this placement, without the priors' pull: lets a caller
        # compare placements made under different priors.
        tokens = np.full(2 * len(labels) + 1, em.blank, dtype=np.int64)
        tokens[1::2] = [lab.token for lab in labels]
        self.last_acoustic_score = float(logp[np.arange(len(path)), tokens[path]].sum())
        return self._spans(path, logp, em, labels)

    # -- building the label sequence -----------------------------------------

    @staticmethod
    def _labels(lines: list[SolverLine], word_gap: int | None,
                line_gap: int | None) -> list[_Label]:
        labels: list[_Label] = []
        if line_gap is not None:
            labels.append(_Label(line_gap, optional=True))
        for li, line in enumerate(lines):
            first = True
            for wi, tokens in enumerate(line.words):
                if not tokens:
                    continue
                optional = line.optional_from is not None and wi >= line.optional_from
                group = li if optional and not first else -1
                if labels and not first and word_gap is not None:
                    labels.append(_Label(word_gap, optional=True, group=group))
                for k, token in enumerate(tokens):
                    labels.append(_Label(token, optional=False, line=li, word=wi,
                                         first_of_line=first and k == 0, group=group))
                first = False
            if not first:
                gap = line_gap if line_gap is not None else word_gap
                if gap is not None:
                    labels.append(_Label(gap, optional=True))
        return labels

    # -- Viterbi --------------------------------------------------------------

    def _viterbi(self, logp: np.ndarray, em: Emissions, labels: list[_Label],
                 lines: list[SolverLine], prior_offset: float) -> np.ndarray:
        frames = logp.shape[0]
        n = len(labels)
        states = 2 * n + 1
        tokens = np.full(states, em.blank, dtype=np.int64)
        tokens[1::2] = [lab.token for lab in labels]
        label_tokens = tokens[1::2]
        optional = np.array([lab.optional for lab in labels])

        # Allowed jumps into each label state (odd s): from s-2 when the token differs from the
        # previous label; from s-3 / s-4 over an optional label before it.
        skip2 = np.zeros(states, dtype=bool)
        skip3 = np.zeros(states, dtype=bool)
        skip4 = np.zeros(states, dtype=bool)
        for k in range(1, n):
            s = 2 * k + 1
            skip2[s] = label_tokens[k] != label_tokens[k - 1]
            if optional[k - 1] and k >= 2:
                skip3[s] = True
                skip4[s] = label_tokens[k] != label_tokens[k - 2]
        jump_to, jump_from = self._group_jumps(labels, label_tokens, optional)
        # An optional first label may be skipped from the start.
        prior_states, prior_frames = [], []
        for k, lab in enumerate(labels):
            if lab.first_of_line and lines[lab.line].prior_start is not None:
                prior_states.append(2 * k + 1)
                prior_frames.append((lines[lab.line].prior_start + prior_offset)
                                    / em.frame_seconds)
        prior_states = np.array(prior_states, dtype=np.int64)
        prior_frames = np.array(prior_frames)
        window_states, window_lo, window_hi = [], [], []
        for k, lab in enumerate(labels):
            line = lines[lab.line] if lab.line >= 0 else None
            if line is None or line.prior_start is None or line.prior_end is None:
                continue
            window_states.append(2 * k + 1)
            window_lo.append((line.prior_start + prior_offset - self._window_tolerance)
                             / em.frame_seconds)
            window_hi.append((line.prior_end + prior_offset + self._window_tolerance)
                             / em.frame_seconds)
        window_states = np.array(window_states, dtype=np.int64)
        window_lo, window_hi = np.array(window_lo), np.array(window_hi)
        window_per_frame = self._window_weight * em.frame_seconds
        tolerance = self._tolerance / em.frame_seconds
        per_frame = self._weight * em.frame_seconds

        inner = np.zeros(states, dtype=bool)
        between = np.zeros(states, dtype=bool)
        line_of = [lab.line for lab in labels]
        for k in range(1, n):
            if labels[k].word >= 0 and labels[k].word == labels[k - 1].word                     and labels[k].line == labels[k - 1].line:
                inner[2 * k] = True  # the blank between two sounds of one word
        if self._together:
            # Everything from a line's first sound to its last: blanks and word gaps.
            for k in range(1, n):
                before = max((j for j in range(k) if line_of[j] >= 0), default=None)
                after = next((j for j in range(k, n) if line_of[j] >= 0), None)
                if before is not None and after is not None and line_of[before] == line_of[after]:
                    between[2 * k] = True
                    if labels[k].line < 0:
                        between[2 * k + 1] = True
        inner_states = np.flatnonzero(inner) if self._inner_blank else np.array([], dtype=np.int64)
        between_states = np.flatnonzero(between & ~inner)

        def emit_at(t: int) -> np.ndarray:
            emit = logp[t, tokens]
            if prior_states.size or window_states.size or inner_states.size or                     between_states.size:
                emit = emit.copy()
            if inner_states.size:
                emit[inner_states] -= self._inner_blank
            if between_states.size:
                emit[between_states] -= self._together
            if prior_states.size:
                distance = np.maximum(0.0, np.abs(t - prior_frames) - tolerance)
                emit[prior_states] -= distance * per_frame
            if window_states.size:
                outside = np.maximum(0.0, np.maximum(window_lo - t, t - window_hi))
                emit[window_states] -= outside * window_per_frame
            return emit

        far = max((t - f for t, f in zip(jump_to, jump_from, strict=True)), default=0)
        back = np.zeros((frames, states), dtype=np.int8 if far < 127 else np.int16)
        first = emit_at(0)
        alpha = np.full(states, self.NEG)
        alpha[0] = first[0]
        alpha[1] = first[1]
        if optional[0] and states > 3:
            alpha[3] = first[3]
        for t in range(1, frames):
            stacked = np.stack((alpha, self._shift(alpha, 1),
                                np.where(skip2, self._shift(alpha, 2), self.NEG),
                                np.where(skip3, self._shift(alpha, 3), self.NEG),
                                np.where(skip4, self._shift(alpha, 4), self.NEG)))
            choice = np.argmax(stacked, axis=0)
            best = np.take_along_axis(stacked, choice[None], axis=0)[0]
            if jump_to.size:
                # Over a whole optional block: ascending, so the best origin is written last.
                cand = alpha[jump_from]
                order = np.argsort(cand)
                better = cand[order] > best[jump_to[order]]
                targets, origins = jump_to[order][better], jump_from[order][better]
                best[targets] = alpha[origins]
                choice[targets] = targets - origins
            alpha = best + emit_at(t)
            back[t] = choice

        # End in the last blank or label, or past an optional last label.
        ends = [states - 1, states - 2]
        if optional[-1] and states >= 4:
            ends += [states - 3, states - 4]
        ends += self._group_ends(labels)
        s = max(ends, key=lambda e: alpha[e])
        path = np.empty(frames, dtype=np.int64)
        for t in range(frames - 1, -1, -1):
            path[t] = s
            s -= int(back[t, s])
        return path

    @staticmethod
    def _blocks(labels: list[_Label]) -> list[tuple[int, int]]:
        """(first, last) label index of every optional block."""
        blocks: list[tuple[int, int]] = []
        for k, lab in enumerate(labels):
            if lab.group < 0:
                continue
            if blocks and labels[blocks[-1][1]].group == lab.group and blocks[-1][1] == k - 1:
                blocks[-1] = (blocks[-1][0], k)
            else:
                blocks.append((k, k))
        return blocks

    def _group_jumps(self, labels: list[_Label], label_tokens: np.ndarray,
                     optional: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """State pairs (to, from) that skip a whole optional block: from the label or blank
        before it to the next label, or past an optional gap after it."""
        to, frm = [], []
        n = len(labels)
        for a, b in self._blocks(labels):
            targets = [c for c in (b + 1, b + 2) if c < n and (c == b + 1 or optional[b + 1])]
            for c in targets:
                if a >= 1 and label_tokens[a - 1] != label_tokens[c]:
                    to.append(2 * c + 1)
                    frm.append(2 * (a - 1) + 1)
                to.append(2 * c + 1)
                frm.append(2 * a)
        return np.array(to, dtype=np.int64), np.array(frm, dtype=np.int64)

    def _group_ends(self, labels: list[_Label]) -> list[int]:
        """A song may end before an optional block at its very end."""
        n = len(labels)
        out = []
        for a, b in self._blocks(labels):
            if b == n - 1 or (b == n - 2 and labels[n - 1].optional):
                out += [2 * a] + ([2 * (a - 1) + 1] if a >= 1 else [])
        return out

    @classmethod
    def _shift(cls, values: np.ndarray, by: int) -> np.ndarray:
        """values moved `by` states later; the first `by` states get nothing."""
        out = np.full_like(values, cls.NEG)
        if by < len(values):
            out[by:] = values[:-by]
        return out

    # -- reading the path -----------------------------------------------------

    @staticmethod
    def _spans(path: np.ndarray, logp: np.ndarray, em: Emissions,
               labels: list[_Label]) -> list[WordSpan]:
        label_frames: dict[int, list[int]] = {}
        for t, s in enumerate(path):
            if s % 2 == 1:
                label_frames.setdefault((s - 1) // 2, []).append(t)
        words: dict[tuple[int, int], WordSpan] = {}
        for k, lab in enumerate(labels):
            if lab.word < 0:
                continue
            frames = label_frames.get(k)
            if not frames:
                continue  # cannot happen for a required label; guards a degenerate path
            probs = np.exp(logp[frames, lab.token])
            # CTC may stay in a token long after it stopped hearing it (the next line is already
            # being sung): the token ends where the model last heard it clearly.
            heard = np.flatnonzero(probs >= GlobalCtcSolver.TRIM * probs.max())
            last = int(heard[-1]) if heard.size else len(frames) - 1
            span = TokenSpan(frames[0], frames[last] + 1, float(probs[:last + 1].mean()))
            key = (lab.line, lab.word)
            if key not in words:
                words[key] = WordSpan(lab.line, lab.word, 0.0, 0.0, 0.0)
            words[key].tokens.append(span)
        for w in words.values():
            w.begin = em.seconds(w.tokens[0].begin)
            w.end = em.seconds(w.tokens[-1].end)
            lengths = [t.end - t.begin for t in w.tokens]
            w.score = float(np.average([t.score for t in w.tokens], weights=lengths))
        return sorted(words.values(), key=lambda w: (w.line, w.word))
