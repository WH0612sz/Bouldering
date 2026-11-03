export interface Draft { path: string; thumb: string; duration: number; size: number; name: string; date: string; submissionId?: string; uploadId?: string; payload?: UploadPayload }
export interface UploadPayload { submission_id: string; name: string; climb_date: string; trim_start: number; trim_end: number; route_id?: string; route_name?: string }
export interface Attempt { id: string; name: string; climb_date: string; completion: string; route_id: string | null; route_name: string | null; duration: number; trim_start: number; trim_end: number; state: string; error: string; revision: number; poster_url: string | null; analysis_message: string; created_at: number }
export interface UploadSession { id: string; state: string; attempt_id: string | null }
export interface Profile { nickname: string; avatar_url: string | null; stats: {videos: number; days: number; routes: number} }
export interface Route { id: string; name: string; count: number }

export type PosePoint = [number, number];
export interface PoseFrame { t: number; points: Record<string, PosePoint>; hip: PosePoint | null }
export interface MotionSpan { start: number; end: number; state: 'MOVING' | 'UNKNOWN' | 'NO_CLEAR_MOVEMENT' }
export interface PoseResult {
  version: string;
  width: number;
  height: number;
  duration: number;
  edges: [number, number][];
  frames: PoseFrame[];
  tracks: {name: string; spans: MotionSpan[]}[];
}
