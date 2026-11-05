from __future__ import annotations

from pathlib import Path

from continuity.context_labels import ContextLabelSet, context_to_mapping
from continuity.models import ContextRecord, SourceRef
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


def make_record(record_id: str, *, label_key: str, label_value: str, summary: str) -> ContextRecord:
    return ContextRecord.new(
        id=record_id,
        kind="artifact_summary",
        title="ifconfig alias syntax",
        summary=summary,
        details="ifconfig alias syntax differs by context partition.",
        tags=["ifconfig", "alias", label_value],
        entities=["ifconfig"],
        confidence=0.9,
        importance=0.8,
        trust_level="corpus_distilled",
        quality={
            "context": context_to_mapping(
                ContextLabelSet(
                    labels={label_key: label_value},
                    partition_keys=frozenset({label_key}),
                    identity_keys=frozenset({"command"}),
                    collision_risk="high",
                )
            )
        },
    )


def make_manpage_record(
    record_id: str,
    *,
    command: str,
    summary: str,
    manual_section: str = "8",
    sources: list[SourceRef] | None = None,
) -> ContextRecord:
    return ContextRecord.new(
        id=record_id,
        kind="artifact_summary",
        title=f"Manpage DESCRIPTION: {command}",
        summary=summary,
        details=f"OpenBSD {command}({manual_section}) details.",
        tags=["openbsd", command, "manpage"],
        entities=[command],
        sources=sources,
        confidence=0.9,
        importance=0.8,
        trust_level="corpus_distilled",
        quality={
            "context": context_to_mapping(
                ContextLabelSet(
                    labels={"os": "openbsd", "command": command, "manual_section": manual_section},
                    partition_keys=frozenset({"os"}),
                    identity_keys=frozenset({"command", "manual_section"}),
                    collision_risk="high",
                )
            )
        },
    )


def seeded_store(tmp_path: Path, records: list[ContextRecord]) -> ContinuityStore:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    for record in records:
        store.upsert_record(record, create_associations=False)
    return store


def ids_for_search(
    store: ContinuityStore,
    query_context: dict[str, object] | None = None,
    *,
    comparison_intent: bool = False,
) -> list[str]:
    return [
        hit.record.id
        for hit in ContinuityRetriever(store, association_enabled=False).search(
            "ifconfig alias syntax",
            query_context=query_context,
            comparison_intent=comparison_intent,
            limit=10,
        )
    ]


def test_query_context_selects_matching_partition_and_rejects_conflict(tmp_path: Path) -> None:
    openbsd = make_record(
        "ifconfig_openbsd",
        label_key="os",
        label_value="openbsd",
        summary="OpenBSD ifconfig alias syntax uses alias address on the interface.",
    )
    linux = make_record(
        "ifconfig_linux",
        label_key="os",
        label_value="linux",
        summary="Linux ifconfig alias syntax commonly uses a colon-suffixed interface.",
    )
    store = seeded_store(tmp_path, [openbsd, linux])

    assert ids_for_search(store, {"labels": {"os": "openbsd"}, "partition_keys": ["os"]}) == [
        "ifconfig_openbsd"
    ]
    assert ids_for_search(store, {"labels": {"os": "linux"}, "partition_keys": ["os"]}) == [
        "ifconfig_linux"
    ]

    debug = ContinuityRetriever(store, association_enabled=False).debug_search(
        "ifconfig alias syntax",
        query_context={"labels": {"os": "openbsd"}, "partition_keys": ["os"]},
        limit=10,
    )
    rejected = {candidate.record.id: candidate.rejected_reason for candidate in debug["rejected"]}
    assert rejected["ifconfig_linux"] == "context_label_conflict:os"


def test_missing_query_context_withholds_high_collision_records(tmp_path: Path) -> None:
    store = seeded_store(
        tmp_path,
        [
            make_record(
                "ifconfig_openbsd",
                label_key="os",
                label_value="openbsd",
                summary="OpenBSD ifconfig alias syntax uses alias address.",
            ),
            make_record(
                "ifconfig_linux",
                label_key="os",
                label_value="linux",
                summary="Linux ifconfig alias syntax uses a colon-suffixed interface.",
            ),
        ],
    )

    debug = ContinuityRetriever(store, association_enabled=False).debug_search(
        "ifconfig alias syntax", limit=10
    )

    assert debug["selected"] == []
    assert {candidate.rejected_reason for candidate in debug["rejected"]} == {
        "missing_partition_context:os"
    }


def test_query_terms_infer_context_for_high_collision_manpage_records(tmp_path: Path) -> None:
    store = seeded_store(
        tmp_path,
        [
            make_manpage_record(
                "openbsd_ldomctl_8",
                command="ldomctl",
                summary="OpenBSD ldomctl can stop guest domains from the primary domain.",
            ),
            make_manpage_record(
                "openbsd_fdisk_8",
                command="fdisk",
                summary="OpenBSD fdisk edits MBR partition tables.",
            ),
        ],
    )

    debug = ContinuityRetriever(store, association_enabled=False).debug_search(
        "How do I stop ldomctl guest domains on OpenBSD sparc64?",
        limit=10,
    )

    assert [candidate.record.id for candidate in debug["selected"]] == ["openbsd_ldomctl_8"]
    rejected = {candidate.record.id: candidate.rejected_reason for candidate in debug["rejected"]}
    assert rejected["openbsd_fdisk_8"] == "context_label_conflict:command"


def test_source_reference_neighbors_do_not_outrank_exact_identity_matches(
    tmp_path: Path,
) -> None:
    daemon = make_manpage_record(
        "openbsd_relayd_8",
        command="relayd",
        manual_section="8",
        summary="OpenBSD relayd daemon reads relayd.conf tables and protocols.",
    )
    relayd_conf = make_manpage_record(
        "openbsd_relayd_conf_5",
        command="relayd.conf",
        manual_section="5",
        summary="OpenBSD relayd.conf defines relay tables, protocols, and forwarding rules.",
    )
    store = seeded_store(tmp_path, [daemon, relayd_conf])
    store.upsert_association_edge(
        "openbsd_relayd_8",
        "openbsd_relayd_conf_5",
        strength=0.95,
        edge_type="source_reference",
    )

    debug = ContinuityRetriever(store, association_enabled=True).debug_search(
        "OpenBSD relayd.conf table protocol forward to",
        query_context={
            "labels": {"os": "openbsd", "command": "relayd.conf", "manual_section": "5"},
            "partition_keys": ["os"],
            "identity_keys": ["command", "manual_section"],
            "collision_risk": "high",
        },
        limit=10,
    )

    selected_ids = [candidate.record.id for candidate in debug["selected"]]
    assert selected_ids[:2] == ["openbsd_relayd_conf_5", "openbsd_relayd_8"]


def test_source_reference_edges_can_bridge_related_manpage_identity_contexts(
    tmp_path: Path,
) -> None:
    ldomctl = make_manpage_record(
        "openbsd_ldomctl_8",
        command="ldomctl",
        summary="OpenBSD ldomctl manages and configures logical domains.",
        sources=[
            SourceRef(
                type="corpus_segment",
                id="ldomctl-description",
                metadata={
                    "outbound_references": [
                        {
                            "target_type": "manpage",
                            "target": "ldom.conf",
                            "section": "5",
                            "raw": "ldom.conf(5)",
                            "relation": "see-also",
                        }
                    ]
                },
            )
        ],
    )
    ldom_conf = make_manpage_record(
        "openbsd_ldom_conf_5",
        command="ldom.conf",
        manual_section="5",
        summary="OpenBSD ldom.conf describes logical domain configuration syntax.",
    )
    fdisk = make_manpage_record(
        "openbsd_fdisk_8",
        command="fdisk",
        summary="OpenBSD fdisk edits MBR partition tables.",
    )
    store = seeded_store(tmp_path, [ldomctl, ldom_conf, fdisk])
    store.upsert_association_edge(
        "openbsd_ldomctl_8",
        "openbsd_ldom_conf_5",
        strength=0.72,
        edge_type="source_reference",
    )

    debug = ContinuityRetriever(store, association_enabled=True).debug_search(
        "How do I configure ldoms with ldomctl on OpenBSD?",
        limit=10,
    )

    selected_ids = [candidate.record.id for candidate in debug["selected"]]
    assert "openbsd_ldomctl_8" in selected_ids
    assert "openbsd_ldom_conf_5" in selected_ids
    assert "openbsd_fdisk_8" not in selected_ids


def test_query_terms_complete_partial_context_for_high_collision_records(tmp_path: Path) -> None:
    store = seeded_store(
        tmp_path,
        [
            make_manpage_record(
                "openbsd_ldomctl_8",
                command="ldomctl",
                summary="OpenBSD ldomctl can stop guest domains from the primary domain.",
            ),
            make_manpage_record(
                "openbsd_fdisk_8",
                command="fdisk",
                summary="OpenBSD fdisk edits MBR partition tables.",
            ),
        ],
    )

    debug = ContinuityRetriever(store, association_enabled=False).debug_search(
        "How do I stop ldomctl guest domains?",
        query_context={"labels": {"os": "openbsd"}, "partition_keys": ["os"]},
        limit=10,
    )

    assert [candidate.record.id for candidate in debug["selected"]] == ["openbsd_ldomctl_8"]
    rejected = {candidate.record.id: candidate.rejected_reason for candidate in debug["rejected"]}
    assert rejected["openbsd_fdisk_8"] == "context_label_conflict:command"


def test_exact_punctuated_label_terms_infer_high_collision_context(tmp_path: Path) -> None:
    store = seeded_store(
        tmp_path,
        [
            make_manpage_record(
                "openbsd_pf_conf_5",
                command="pf.conf",
                manual_section="5",
                summary="OpenBSD pf.conf packet filter configuration syntax.",
            ),
            make_manpage_record(
                "openbsd_smtpd_conf_5",
                command="smtpd.conf",
                manual_section="5",
                summary="OpenBSD smtpd.conf mail daemon configuration syntax.",
            ),
        ],
    )

    debug = ContinuityRetriever(store, association_enabled=False).debug_search(
        "OpenBSD pf.conf syntax",
        limit=10,
    )

    assert [candidate.record.id for candidate in debug["selected"]] == ["openbsd_pf_conf_5"]
    rejected = {candidate.record.id: candidate.rejected_reason for candidate in debug["rejected"]}
    assert rejected["openbsd_smtpd_conf_5"] == "context_label_conflict:command"


def test_specific_punctuated_label_beats_shorter_label_terms(tmp_path: Path) -> None:
    store = seeded_store(
        tmp_path,
        [
            make_manpage_record(
                "openbsd_relayd_conf_5",
                command="relayd.conf",
                manual_section="5",
                summary="OpenBSD relayd.conf defines relay tables and protocols.",
            ),
            make_manpage_record(
                "openbsd_table_5",
                command="table",
                manual_section="5",
                summary="OpenBSD table file format documentation.",
            ),
            make_manpage_record(
                "openbsd_relayd_8",
                command="relayd",
                manual_section="8",
                summary="OpenBSD relayd daemon documentation.",
            ),
        ],
    )

    debug = ContinuityRetriever(store, association_enabled=False).debug_search(
        "OpenBSD relayd.conf table protocol forward to",
        limit=10,
    )

    assert [candidate.record.id for candidate in debug["selected"]] == ["openbsd_relayd_conf_5"]
    rejected = {candidate.record.id: candidate.rejected_reason for candidate in debug["rejected"]}
    assert rejected["openbsd_table_5"] == "context_label_conflict:command"
    assert rejected["openbsd_relayd_8"] == "context_label_conflict:command"


def test_file_format_query_prefers_section_five_over_same_named_command(tmp_path: Path) -> None:
    store = seeded_store(
        tmp_path,
        [
            make_manpage_record(
                "openbsd_group_5",
                command="group",
                manual_section="5",
                summary="OpenBSD group file format for /etc/group.",
            ),
            make_manpage_record(
                "openbsd_group_8",
                command="group",
                manual_section="8",
                summary="OpenBSD group user management command.",
            ),
        ],
    )

    debug = ContinuityRetriever(store, association_enabled=False).debug_search(
        "OpenBSD group file format",
        limit=10,
    )

    assert [candidate.record.id for candidate in debug["selected"]] == ["openbsd_group_5"]
    rejected = {candidate.record.id: candidate.rejected_reason for candidate in debug["rejected"]}
    assert rejected["openbsd_group_8"] == "context_label_conflict:manual_section"


def test_identity_query_context_rejects_other_manpage_commands(tmp_path: Path) -> None:
    store = seeded_store(
        tmp_path,
        [
            make_manpage_record(
                "openbsd_ifconfig_8",
                command="ifconfig",
                summary="Configure network interface addresses and options.",
            ),
            make_manpage_record(
                "openbsd_route_8",
                command="route",
                summary="Manipulate network routing tables and gateways.",
            ),
        ],
    )
    retriever = ContinuityRetriever(store, association_enabled=False)

    debug = retriever.debug_search(
        "configure network interface",
        query_context={
            "labels": {"os": "openbsd", "command": "ifconfig", "manual_section": "8"},
            "partition_keys": ["os"],
            "identity_keys": ["command", "manual_section"],
        },
        limit=10,
    )

    assert [candidate.record.id for candidate in debug["selected"]] == ["openbsd_ifconfig_8"]
    rejected = {candidate.record.id: candidate.rejected_reason for candidate in debug["rejected"]}
    assert rejected["openbsd_route_8"] in {
        "context_label_conflict:command",
        # With IDF-weighted text anchors, weak matches can fall below the
        # base-relevance gate before the context-label conflict is recorded.
        "below_min_base_relevance",
    }


def test_identity_query_context_rejects_unlabeled_manpage_like_records(tmp_path: Path) -> None:
    unlabeled = ContextRecord.new(
        id="unlabeled_openbsd_notes",
        kind="environment_fact",
        title="Fetched OpenBSD manpages",
        summary="Fetched OpenBSD ifconfig route pfctl ac apmd syslogd vmctl ntpd manpages.",
        details="This operational note mentions many OpenBSD section 8 commands but is not a command-specific corpus record.",
        tags=["openbsd", "manpage"],
        entities=["OpenBSD", "ifconfig", "route"],
        confidence=0.9,
        importance=0.8,
        trust_level="built_in_memory_mirror",
    )
    store = seeded_store(
        tmp_path,
        [
            unlabeled,
            make_manpage_record(
                "openbsd_ifconfig_8",
                command="ifconfig",
                summary="Configure network interface addresses and options.",
            ),
        ],
    )
    retriever = ContinuityRetriever(store, association_enabled=False)

    debug = retriever.debug_search(
        "OpenBSD ifconfig interface address",
        query_context={
            "labels": {"os": "openbsd", "command": "ifconfig", "manual_section": "8"},
            "partition_keys": ["os"],
            "identity_keys": ["command", "manual_section"],
            "collision_risk": "high",
        },
        limit=10,
    )

    assert [candidate.record.id for candidate in debug["selected"]] == ["openbsd_ifconfig_8"]
    rejected = {candidate.record.id: candidate.rejected_reason for candidate in debug["rejected"]}
    assert rejected["unlabeled_openbsd_notes"] == "missing_record_context:command"


def test_comparison_intent_allows_conflicting_partitions(tmp_path: Path) -> None:
    store = seeded_store(
        tmp_path,
        [
            make_record(
                "ifconfig_openbsd",
                label_key="os",
                label_value="openbsd",
                summary="OpenBSD ifconfig alias syntax uses alias address.",
            ),
            make_record(
                "ifconfig_linux",
                label_key="os",
                label_value="linux",
                summary="Linux ifconfig alias syntax uses a colon-suffixed interface.",
            ),
        ],
    )

    ids = ids_for_search(store, comparison_intent=True)

    # Both conflicting partitions must be selected; exact order depends on
    # per-signal magnitudes (FTS rank normalization), so assert membership.
    assert set(ids) == {"ifconfig_linux", "ifconfig_openbsd"}


def test_same_generic_gate_handles_customer_and_language_partitions(tmp_path: Path) -> None:
    records = [
        make_record(
            "rollout_acme",
            label_key="customer",
            label_value="acme",
            summary="Acme rollout plan requires canary approval before broad rollout.",
        ),
        make_record(
            "rollout_globex",
            label_key="customer",
            label_value="globex",
            summary="Globex rollout plan requires maintenance-window approval.",
        ),
        make_record(
            "map_rust",
            label_key="language",
            label_value="rust",
            summary="Rust map documentation describes Iterator::map with closures.",
        ),
        make_record(
            "map_python",
            label_key="language",
            label_value="python",
            summary="Python map documentation describes applying a callable to iterables.",
        ),
    ]
    store = seeded_store(tmp_path, records)
    retriever = ContinuityRetriever(store, association_enabled=False)

    customer_hits = retriever.search(
        "rollout plan approval",
        query_context={"labels": {"customer": "acme"}, "partition_keys": ["customer"]},
        limit=10,
    )
    language_hits = retriever.search(
        "map documentation callable closure",
        query_context={"labels": {"language": "python"}, "partition_keys": ["language"]},
        limit=10,
    )

    assert [hit.record.id for hit in customer_hits] == ["rollout_acme"]
    assert [hit.record.id for hit in language_hits] == ["map_python"]


def test_association_graph_cuts_conflicting_context_neighbor(tmp_path: Path) -> None:
    openbsd = make_record(
        "ifconfig_openbsd",
        label_key="os",
        label_value="openbsd",
        summary="OpenBSD ifconfig alias syntax uses alias address.",
    )
    linux = make_record(
        "ifconfig_linux",
        label_key="os",
        label_value="linux",
        summary="Linux details are reachable only through graph activation.",
    )
    store = seeded_store(tmp_path, [openbsd, linux])
    store.upsert_association_edge(
        "ifconfig_openbsd", "ifconfig_linux", strength=1.0, edge_type="semantic_similarity"
    )

    debug = ContinuityRetriever(store).debug_search(
        "ifconfig alias openbsd syntax",
        query_context={"labels": {"os": "openbsd"}, "partition_keys": ["os"]},
        limit=10,
    )

    assert [candidate.record.id for candidate in debug["selected"]] == ["ifconfig_openbsd"]
    assert any(
        cut["record_id"] == "ifconfig_linux" and cut["reason"] == "context_label_conflict"
        for cut in debug["activation_trace"]["cut_neighbors"]
    )


def test_upsert_auto_creates_source_reference_edges_for_identity_targets(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        make_manpage_record(
            "openbsd_ldom_conf_5",
            command="ldom.conf",
            manual_section="5",
            summary="Configuration file grammar.",
        )
    )
    for index in range(5):
        store.upsert_record(
            make_manpage_record(
                f"aaa_noise_{index}",
                command=f"noise{index}",
                summary=f"Unrelated daemon reference {index}.",
            )
        )

    store.upsert_record(
        make_manpage_record(
            "openbsd_ldomctl_8",
            command="ldomctl",
            summary="Domain control utility.",
            sources=[
                SourceRef(
                    type="corpus_segment",
                    id="ldomctl-description",
                    metadata={
                        "outbound_references": [
                            {
                                "target_type": "manpage",
                                "target": "ldom.conf",
                                "section": "5",
                                "raw": "ldom.conf(5)",
                                "relation": "see-also",
                            }
                        ]
                    },
                )
            ],
        ),
        candidate_limit=1,
    )

    edges = store.list_association_edges("openbsd_ldomctl_8")
    assert [(edge.memory_id_b, edge.edge_type) for edge in edges] == [
        ("openbsd_ldom_conf_5", "source_reference")
    ]
