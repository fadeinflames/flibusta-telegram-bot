import { createContext, useContext, useState, useRef, useCallback, useEffect } from 'react'
import type { ReactNode } from 'react'
import { api, getStreamUrl } from '../api/client'

interface Track {
  topicId: string
  fileIndex: number
  title: string
  author: string
  chapterName: string
}

interface AudioPlayerState {
  currentTrack: Track | null
  isPlaying: boolean
  currentTime: number
  duration: number
  playbackRate: number
  chapters: { name: string; index: number }[]
}

interface AudioPlayerActions {
  play: (track: Track, chapters?: { name: string; index: number }[]) => void
  pause: () => void
  resume: () => void
  toggle: () => void
  seekTo: (time: number) => void
  setRate: (rate: number) => void
  nextChapter: () => void
  prevChapter: () => void
  stop: () => void
}

type AudioPlayerContextType = AudioPlayerState & AudioPlayerActions

const AudioPlayerContext = createContext<AudioPlayerContextType | null>(null)

const defaultState: AudioPlayerContextType = {
  currentTrack: null,
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  playbackRate: 1,
  chapters: [],
  play: () => {},
  pause: () => {},
  resume: () => {},
  toggle: () => {},
  seekTo: () => {},
  setRate: () => {},
  nextChapter: () => {},
  prevChapter: () => {},
  stop: () => {},
}

export function useAudioPlayer() {
  const ctx = useContext(AudioPlayerContext)
  return ctx || defaultState
}

const PLAYBACK_RATES = [0.75, 1, 1.25, 1.5, 2]

export function AudioPlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const saveTimerRef = useRef<ReturnType<typeof setInterval>>()

  const [currentTrack, setCurrentTrack] = useState<Track | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playbackRate, setPlaybackRate] = useState(1)
  const [chapters, setChapters] = useState<{ name: string; index: number }[]>([])

  // Initialize audio element once
  useEffect(() => {
    const audio = new Audio()
    audio.preload = 'metadata'
    audioRef.current = audio

    audio.addEventListener('timeupdate', () => setCurrentTime(audio.currentTime))
    audio.addEventListener('durationchange', () => setDuration(audio.duration || 0))
    audio.addEventListener('play', () => setIsPlaying(true))
    audio.addEventListener('pause', () => setIsPlaying(false))
    audio.addEventListener('ended', () => setIsPlaying(false))

    return () => {
      audio.pause()
      audio.src = ''
      clearInterval(saveTimerRef.current)
    }
  }, [])

  // Auto-save progress every 10 seconds
  useEffect(() => {
    clearInterval(saveTimerRef.current)
    if (currentTrack && isPlaying) {
      saveTimerRef.current = setInterval(() => {
        if (currentTrack) {
          api.updateAudioProgress(currentTrack.topicId, { chapter: currentTrack.fileIndex }).catch(() => {})
        }
      }, 10_000)
    }
    return () => clearInterval(saveTimerRef.current)
  }, [currentTrack, isPlaying])

  const play = useCallback((track: Track, newChapters?: { name: string; index: number }[]) => {
    const audio = audioRef.current
    if (!audio) return

    const url = getStreamUrl(track.topicId, track.fileIndex)
    audio.src = url
    audio.playbackRate = playbackRate
    audio.play().catch(() => {})
    setCurrentTrack(track)
    if (newChapters) setChapters(newChapters)
  }, [playbackRate])

  const pause = useCallback(() => {
    audioRef.current?.pause()
  }, [])

  const resume = useCallback(() => {
    audioRef.current?.play().catch(() => {})
  }, [])

  const toggle = useCallback(() => {
    if (isPlaying) pause()
    else resume()
  }, [isPlaying, pause, resume])

  const seekTo = useCallback((time: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = time
    }
  }, [])

  const setRate = useCallback((rate: number) => {
    setPlaybackRate(rate)
    if (audioRef.current) {
      audioRef.current.playbackRate = rate
    }
  }, [])

  const nextChapter = useCallback(() => {
    if (!currentTrack || chapters.length === 0) return
    const currentIdx = chapters.findIndex(c => c.index === currentTrack.fileIndex)
    if (currentIdx < chapters.length - 1) {
      const next = chapters[currentIdx + 1]
      play({ ...currentTrack, fileIndex: next.index, chapterName: next.name }, chapters)
    }
  }, [currentTrack, chapters, play])

  const prevChapter = useCallback(() => {
    if (!currentTrack || chapters.length === 0) return
    const currentIdx = chapters.findIndex(c => c.index === currentTrack.fileIndex)
    if (currentIdx > 0) {
      const prev = chapters[currentIdx - 1]
      play({ ...currentTrack, fileIndex: prev.index, chapterName: prev.name }, chapters)
    }
  }, [currentTrack, chapters, play])

  const stop = useCallback(() => {
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.src = ''
    }
    setCurrentTrack(null)
    setIsPlaying(false)
    setCurrentTime(0)
    setDuration(0)
    setChapters([])
  }, [])

  return (
    <AudioPlayerContext.Provider
      value={{
        currentTrack,
        isPlaying,
        currentTime,
        duration,
        playbackRate,
        chapters,
        play,
        pause,
        resume,
        toggle,
        seekTo,
        setRate,
        nextChapter,
        prevChapter,
        stop,
      }}
    >
      {children}
    </AudioPlayerContext.Provider>
  )
}
