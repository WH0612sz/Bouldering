"""Generate sampled 2D pose and movement data from the playback proxy."""
import json
import sys
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

PARTS = {'左手': (15,), '右手': (16,), '左脚': (27,), '右脚': (28,), '髋部': (23, 24)}
EDGES = [(11,12),(11,13),(13,15),(12,14),(14,16),(11,23),(12,24),(23,24),
         (23,25),(25,27),(24,26),(26,28),(27,31),(28,32)]
JOINTS = sorted({joint for edge in EDGES for joint in edge})


def background(frame, poses):
    gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (180, 320))
    mask = np.full(gray.shape, 255, np.uint8)
    for pose in poses:
        coords = np.array([(p.x * 180, p.y * 320) for p in pose if p.visibility >= .5])
        if len(coords):
            low = np.clip(coords.min(axis=0) - 10, [0, 0], [179, 319]).astype(int)
            high = np.clip(coords.max(axis=0) + 10, [0, 0], [179, 319]).astype(int)
            cv2.rectangle(mask, tuple(low), tuple(high), 0, -1)
    return gray, mask


def camera_stable(previous, gray, elapsed):
    if previous is None:
        return False
    old, mask = previous
    points = cv2.goodFeaturesToTrack(old, 120, .01, 10, mask=mask)
    if points is None or len(points) < 8:
        return False
    tracked, status, _ = cv2.calcOpticalFlowPyrLK(old, gray, points, None)
    if tracked is None or status is None or status.sum() < 8:
        return False
    valid = status.ravel() == 1
    matrix, inliers = cv2.estimateAffinePartial2D(points[valid], tracked[valid], method=cv2.RANSAC)
    if matrix is None or inliers.sum() < 8:
        return False
    # Check several image locations so zoom and rotation are also detected.
    probes = np.array([[90., 160., 1.], [30., 50., 1.], [150., 270., 1.]])
    shift = np.linalg.norm(probes @ matrix.T - probes[:, :2], axis=1).max()
    return shift / np.hypot(180, 320) / elapsed <= .025


def keypoints(poses):
    # With ambiguous identity, suppress observations until one subject is visible.
    if len(poses) != 1:
        return {}
    pose = poses[0]
    return {str(j): [round(pose[j].x, 4), round(pose[j].y, 4)] for j in JOINTS
            if min(pose[j].visibility, pose[j].presence) >= .6
            and 0 <= pose[j].x <= 1 and 0 <= pose[j].y <= 1}


def midpoint(points, joints):
    selected = [points.get(str(j)) for j in joints]
    return np.mean(selected, axis=0).tolist() if all(p is not None for p in selected) else None


def movement_tracks(frames, stable, duration, width, height):
    sizes = []
    for frame in frames:
        values = [frame['points'].get(str(j)) for j in (11,12,23,24,25,26,27,28)]
        visible = [p[1] for p in values if p is not None]
        if len(visible) >= 6:
            sizes.append(np.ptp(visible) * height)
    scale = max(float(np.median(sizes)), height * .10) if sizes else height * .30
    tracks = []
    for name, joints in PARTS.items():
        spans = []
        moving = False
        for i, frame in enumerate(frames):
            before = frames[i - 1] if i else frame
            elapsed = frame['t'] - before['t']
            start = midpoint(before['points'], joints)
            end = midpoint(frame['points'], joints)
            state = 'UNKNOWN'
            if start is not None and end is not None and 0 < elapsed <= .25 and stable[i]:
                speed = np.linalg.norm((np.array(end) - start) * [width, height]) / scale / elapsed
                moving = speed > (.07 if moving else .12)
                state = 'MOVING' if moving else 'NO_CLEAR_MOVEMENT'
            else:
                moving = False
            until = frames[i + 1]['t'] if i + 1 < len(frames) else duration
            if spans and spans[-1]['state'] == state:
                spans[-1]['end'] = until
            else:
                spans.append({'start': frame['t'], 'end': until, 'state': state})
        for span in spans:
            if span['state'] == 'MOVING' and span['end'] - span['start'] < .2:
                span['state'] = 'UNKNOWN'
        tracks.append({'name': name, 'spans': spans})
    return tracks


def analyze(source, model):
    cv2.setNumThreads(1)
    capture = cv2.VideoCapture(str(source))
    fps = capture.get(cv2.CAP_PROP_FPS)
    count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0 or count <= 0 or width <= 0 or height <= 0:
        capture.release()
        raise ValueError('Invalid playback proxy')
    duration = count / fps
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_poses=3,
    )
    frames, stable = [], []
    previous = None
    next_sample = 0
    index = 0
    try:
        with mp.tasks.vision.PoseLandmarker.create_from_options(options) as detector:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
                if frames and timestamp <= frames[-1]['t']:
                    timestamp = index / fps
                index += 1
                if timestamp + .00001 < next_sample:
                    continue
                timestamp = round(timestamp, 4)
                next_sample = timestamp + .095
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                poses = detector.detect_for_video(image, round(timestamp * 1000)).pose_landmarks
                gray, mask = background(frame, poses)
                elapsed = timestamp - frames[-1]['t'] if frames else .1
                stable.append(elapsed > 0 and camera_stable(previous, gray, elapsed))
                previous = gray, mask
                points = keypoints(poses)
                frames.append({'t': timestamp, 'points': points,
                               'hip': midpoint(points, PARTS['髋部']) if stable[-1] else None})
    finally:
        capture.release()
    if not frames:
        raise ValueError('No frames decoded')
    duration = max(duration, frames[-1]['t'] + 1 / fps)
    return {'version': 'pose-v1', 'duration': duration, 'width': width, 'height': height,
            'edges': EDGES, 'frames': frames,
            'tracks': movement_tracks(frames, stable, duration, width, height)}


if __name__ == '__main__':
    source, model, destination = map(Path, sys.argv[1:])
    result = analyze(source, model)
    destination.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
