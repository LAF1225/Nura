// Nura's first words (PRD 2, section 38).
//
// The robot has no speaker yet, so audio is compiled out by default and the
// introduction is logged instead. With NURA_HAS_AUDIO=1 this drives an I2S
// amplifier.
//
// The spoken line -- "Hi. I'm Nura. It's nice to meet you." -- needs a
// recorded or synthesised clip, which does not exist yet. Until it does, a
// fitted speaker plays a short two-note chime so the moment is not silent.
// This is explicitly a placeholder (PRD 2, section 38 allows the simplest
// maintainable method, documented as temporary).
#pragma once

#include <Arduino.h>

namespace nura::audio {

void begin();

//: Plays the introduction. Returns false if nothing could be played.
bool playIntroduction();

bool isFitted();

}  // namespace nura::audio
