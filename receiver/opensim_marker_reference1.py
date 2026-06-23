import opensim as osim


def make_markers_reference_from_packet(
    packet,
    marker_names,
    marker_weights,
):
    """
    单帧 MarkerFramePacket -> OpenSim MarkersReference
    """
    table = osim.TimeSeriesTableVec3()

    labels = osim.StdVectorString()
    for name in marker_names:
        labels.append(name)

    table.setColumnLabels(labels)

    row = osim.RowVectorVec3(
        len(marker_names),
        osim.Vec3(0.0, 0.0, 0.0),
    )

    for i, name in enumerate(marker_names):
        x, y, z = packet.markers[name]
        row[i] = osim.Vec3(float(x), float(y), float(z))

    table.appendRow(float(packet.time), row)

    markers_reference = osim.MarkersReference(
        table,
        marker_weights,
    )

    return markers_reference


def make_markers_reference_from_packets(
    packets,
    marker_names,
    marker_weights,
):
    """
    多帧 MarkerFramePacket -> OpenSim MarkersReference
    用于 chunk IK：一个 chunk 只创建一次 MarkersReference + IK Solver
    """
    if not packets:
        raise ValueError("packets is empty")

    table = osim.TimeSeriesTableVec3()

    labels = osim.StdVectorString()
    for name in marker_names:
        labels.append(name)

    table.setColumnLabels(labels)

    last_time = None

    for packet in packets:
        current_time = float(packet.time)

        if last_time is not None and current_time <= last_time:
            raise ValueError(
                f"Packet time must be strictly increasing. "
                f"last_time={last_time}, current_time={current_time}, "
                f"frame_index={packet.frame_index}"
            )

        row = osim.RowVectorVec3(
            len(marker_names),
            osim.Vec3(0.0, 0.0, 0.0),
        )

        for i, name in enumerate(marker_names):
            x, y, z = packet.markers[name]
            row[i] = osim.Vec3(float(x), float(y), float(z))

        table.appendRow(current_time, row)
        last_time = current_time

    markers_reference = osim.MarkersReference(
        table,
        marker_weights,
    )

    return markers_reference
