"""Literal evidence computations; never an authenticity or adequacy certificate."""


def _span(text, words, start, size):
    left, right = words[start][1], words[start + size - 1][2]
    preview_end = min(right, left + 240)
    return {'start': left, 'end': preview_end, 'quote': text[left:preview_end],
            'window_end': right, 'quote_truncated': preview_end < right}


def source_overlap(item, backend):
    words, size = item['manuscript_tokens'], item['min_tokens']
    values = [word[0] for word in words]
    windows = [tuple(values[i:i + size]) for i in range(max(0, len(words) - size + 1))]
    sources, unknown = [], []
    for source in item['sources']:
        index = {}
        source_values = [word[0] for word in source['tokens']]
        comparable = len(words) >= size and len(source_values) >= size
        if not comparable:
            unknown.append(source['id'])
        for i in range(max(0, len(source_values) - size + 1)):
            index.setdefault(tuple(source_values[i:i + size]), i)
        differences, examples, count = [0] * (len(words) + 1), [], 0
        for i, window in enumerate(windows):
            if window not in index:
                continue
            count += 1
            differences[i] += 1
            differences[i + size] -= 1
            if len(examples) < 100:
                examples.append({'manuscript': _span(item['text'], words, i, size),
                                 'source': _span(source['text'], source['tokens'], index[window], size)})
        active, matched = 0, 0
        for delta in differences[:-1]:
            active += delta
            matched += int(active > 0)
        sources.append({'id': source['id'], 'sha256': source['sha256'],
                        'comparison_status': 'compared' if comparable else 'insufficient_tokens',
                        'source_tokens': len(source_values), 'matched_tokens': matched,
                        'matching_windows': count, 'examples': examples, 'examples_truncated': count > 100})
    return 'UNDETERMINED' if unknown else 'CANDIDATES', {'text_sha256': item['text_sha256'], 'manuscript_tokens': len(words),
                          'min_tokens': size, 'sources': sources, 'unassessed_checks': unknown,
                          'normalization': 'Unicode word runs (Python re \\w+), casefold; no other normalization.',
                          'alignment': 'Earliest source occurrence per matching manuscript window; first 100 examples per source.',
                          'meaning': 'Lexical overlap with supplied sources only. Counts are union manuscript tokens per source, not a plagiarism or novelty score. Quotes, bibliography and common phrases are not excluded. Attribution and relevance require human review.'}


def protocol_consistency(item, backend):
    rows, unknown = [], []
    for field in item['fields']:
        left, right = field['protocol'], field['manuscript']
        comparison = 'unknown' if left is None or right is None else (
            'equal' if left['value'] == right['value'] else 'different')
        if comparison == 'unknown':
            unknown.append(field['id'])
        rows.append(dict(field, comparison=comparison))
    different = sum(row['comparison'] == 'different' for row in rows)
    status = 'UNDETERMINED' if unknown else 'REFUTED' if different else 'VERIFIED'
    return status, {'text_sha256': item['text_sha256'], 'protocol_sha256': item['protocol']['sha256'],
                    'fields': rows, 'differences': different, 'unassessed_checks': unknown,
                    'meaning': 'Case-sensitive literal equality of caller-mapped strings only; VERIFIED means all supplied mapped values match. Quotes anchor mappings but do not verify their semantic correctness, protocol authenticity, prospective registration, complete field selection or justified amendments. Null mappings remain unknown; observed differences are retained.'}


def checklist_evidence(item, backend):
    mapped = {row['id']: row for row in item['assessments']}
    rows, unknown = [], []
    counts = dict.fromkeys(('reported', 'not_applicable', 'unknown', 'unmapped'), 0)
    for requirement in item['checklist']['items']:
        assessment = mapped.get(requirement['id'], {'status': 'unmapped'})
        status = assessment['status']
        counts[status] += 1
        if status in ('unknown', 'unmapped'):
            unknown.append(requirement['id'])
        rows.append(dict(requirement, **{key: value for key, value in assessment.items() if key != 'id'}))
    return 'UNDETERMINED' if unknown else 'CANDIDATES', {
        'text_sha256': item['text_sha256'], 'checklist_sha256': item['checklist_sha256'],
        'checklist_name': item['checklist']['name'], 'checklist_version': item['checklist']['version'],
        'items': rows, 'counts': counts, 'unassessed_checks': unknown,
        'meaning': 'Coverage of caller-supplied checklist records only. Reported quotes occur in the manuscript; relevance, adequacy and exclusion rationales remain caller judgments. Checklist authenticity, completeness, study appropriateness and official guideline compliance are not verified.'}
