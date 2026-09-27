export async function transcribeDeepgram(audio, contentType, key = process.env.DEEPGRAM_API_KEY) {
  if (!key) throw new Error('Set DEEPGRAM_API_KEY in your user-profile .phone-control/.env file, then restart the companion.');
  const response = await fetch('https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true', {
    method: 'POST',
    headers: { Authorization: `Token ${key}`, 'Content-Type': contentType },
    body: audio,
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) throw new Error(`Deepgram transcription failed (${response.status}).`);
  const result = await response.json();
  const transcript = result.results?.channels?.[0]?.alternatives?.[0]?.transcript?.trim();
  if (!transcript) throw new Error('No speech was recognized. Try speaking closer to the microphone.');
  return transcript;
}
