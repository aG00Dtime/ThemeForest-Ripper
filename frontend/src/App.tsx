import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  Container,
  Flex,
  Heading,
  Input,
  Link,
  Spinner,
  Stack,
  Text,
  VStack,
  useToken
} from "@chakra-ui/react";
import { FaGithub } from "react-icons/fa6";
import {
  RipJobLogEntry,
  RipJobView,
  createJob,
  fetchJob,
  fetchLogs
} from "./api";

const STORAGE_KEY = "themeRipper.activeJob";

type SubmissionState = "idle" | "submitting";

const STATUS_LABEL: Record<RipJobView["status"], string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Completed",
  failed: "Failed"
};

const STATUS_COLOR: Record<RipJobView["status"], string> = {
  queued: "purple",
  running: "blue",
  succeeded: "green",
  failed: "red"
};

const LEVEL_LABEL: Record<string, string> = {
  info: "Info",
  warn: "Warning",
  warning: "Warning",
  error: "Error"
};

const LEVEL_COLOR: Record<string, string> = {
  info: "blue",
  warn: "yellow",
  warning: "yellow",
  error: "red"
};

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

export default function App() {
  const [themeUrl, setThemeUrl] = useState("");
  const [submission, setSubmission] = useState<SubmissionState>("idle");
  const [job, setJob] = useState<RipJobView | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [logEntries, setLogEntries] = useState<RipJobLogEntry[]>([]);
  const [logError, setLogError] = useState<string | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const logCursorRef = useRef(0);
  const jobRef = useRef<RipJobView | null>(null);
  const logContainerRef = useRef<HTMLDivElement | null>(null);
  const [bgStart, bgEnd] = useToken("colors", ["backgroundGradientStart", "backgroundGradientEnd"]);
  const expiresAt = useMemo(() => (job?.expires_at ? new Date(job.expires_at) : null), [job?.expires_at]);
  const isExpired = useMemo(() => (expiresAt ? expiresAt.getTime() <= Date.now() : false), [expiresAt]);
  const expiresLabel = useMemo(() => {
    if (!expiresAt) {
      return null;
    }
    const options: Intl.DateTimeFormatOptions = {
      hour: "2-digit",
      minute: "2-digit",
      month: "short",
      day: "numeric"
    };
    return expiresAt.toLocaleString(undefined, options);
  }, [expiresAt]);

  useEffect(() => {
    let cancelled = false;
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return;
    }

    try {
      const saved = JSON.parse(raw) as { jobId?: string; themeUrl?: string } | null;
      if (!saved?.jobId) {
        window.localStorage.removeItem(STORAGE_KEY);
        return;
      }

      const restore = async () => {
        try {
          const restoredJob = await fetchJob(saved.jobId!);
          if (cancelled) {
            return;
          }
          setThemeUrl(saved.themeUrl ?? "");
          setJob(restoredJob);
          try {
            const logs = await fetchLogs(saved.jobId!, 0);
            if (cancelled) {
              return;
            }
            setLogEntries(logs.entries);
            logCursorRef.current = logs.next_cursor;
          } catch (logErr) {
            if (!cancelled) {
              setLogError((logErr as Error).message);
            }
          }
        } catch (error) {
          if (!cancelled) {
            window.localStorage.removeItem(STORAGE_KEY);
            setGlobalError("Previous job could not be restored (it may have expired).");
          }
        }
      };

      void restore();
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    jobRef.current = job;
  }, [job]);

  useEffect(() => {
    if (!job) {
      setLogEntries([]);
      logCursorRef.current = 0;
      return;
    }
    setLogError(null);
    setLogEntries(job.log_tail.entries);
    logCursorRef.current = job.log_tail.next_cursor;

    let cancelled = false;

    const pollLogs = async () => {
      if (!jobRef.current) {
        return;
      }
      try {
        const data = await fetchLogs(jobRef.current.job_id, logCursorRef.current);
        if (cancelled) {
          return;
        }
        if (data.entries.length > 0) {
          setLogEntries(prev => [...prev, ...data.entries]);
          logCursorRef.current = data.next_cursor;
        }
      } catch (error) {
        if (!cancelled) {
          setLogError((error as Error).message);
        }
      }
    };

    const interval = window.setInterval(() => {
      const status = jobRef.current?.status;
      if (status === "succeeded" || status === "failed") {
        if (!cancelled) {
          void pollLogs();
        }
        return;
      }
      void pollLogs();
    }, 2000);

    void pollLogs();

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [job?.job_id]);

  useEffect(() => {
    if (!job) {
      return;
    }

    let cancelled = false;

    const pollJob = async () => {
      const current = jobRef.current;
      if (!current) {
        return;
      }
      if (current.status === "succeeded" || current.status === "failed") {
        return;
      }
      try {
        const updated = await fetchJob(current.job_id);
        if (!cancelled) {
          setJob(updated);
          setJobError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setJobError((error as Error).message);
        }
      }
    };

    const interval = window.setInterval(() => {
      void pollJob();
    }, 2000);

    void pollJob();

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [job?.job_id]);

  useEffect(() => {
    if (!logContainerRef.current) {
      return;
    }
    logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
  }, [logEntries]);

  const statusBadge = useMemo(() => {
    if (!job) {
      return null;
    }
    return (
      <Badge colorScheme={STATUS_COLOR[job.status]} variant="solid" px={3} py={1} borderRadius="full">
        {STATUS_LABEL[job.status]}
      </Badge>
    );
  }, [job]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!themeUrl) {
      return;
    }
    setSubmission("submitting");
    setGlobalError(null);
    try {
      const trimmedUrl = themeUrl.trim();
      const nextJob = await createJob(trimmedUrl);
      setJob(nextJob);
      setLogEntries(nextJob.log_tail.entries);
      logCursorRef.current = nextJob.log_tail.next_cursor;
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ jobId: nextJob.job_id, themeUrl: trimmedUrl })
      );
    } catch (error) {
      setGlobalError((error as Error).message);
    } finally {
      setSubmission("idle");
    }
  };

  const handleClearJob = () => {
    window.localStorage.removeItem(STORAGE_KEY);
    setJob(null);
    setLogEntries([]);
    setJobError(null);
    setLogError(null);
    setGlobalError(null);
    logCursorRef.current = 0;
  };

  const canSubmit = submission === "idle" && themeUrl.trim().length > 0;
  const downloadAvailable = Boolean(job?.status === "succeeded" && job.download_url && !isExpired);

  return (
    <Box
      minH="100vh"
      bgGradient={`linear(120deg, ${bgStart} 0%, ${bgEnd} 100%)`}
      py={{ base: 8, md: 12 }}
      px={4}
    >
      <Container maxW="container.lg">
        <Box
          bg="surface"
          borderWidth="1px"
          borderColor="whiteAlpha.100"
          borderRadius="2xl"
          shadow="2xl"
          p={{ base: 6, md: 10 }}
        >
          <Flex justify="space-between" align={{ base: "flex-start", md: "center" }} gap={4}>
            <Box>
              <Heading size="lg" mb={2} color="textPrimary">
                Theme Ripper
              </Heading>
              <Text color="textSecondary">
                Rip ThemeForest previews and package the assets for download.
              </Text>
            </Box>
            <Badge colorScheme="brand" variant="outline" px={3} py={1} borderRadius="full">
              beta
            </Badge>
          </Flex>

          <Box as="form" onSubmit={handleSubmit} mt={8}>
            <Stack direction={{ base: "column", md: "row" }} spacing={4}>
              <Input
                type="url"
                required
                aria-label="ThemeForest URL"
                placeholder="https://themeforest.net/item/..."
                value={themeUrl}
                onChange={event => setThemeUrl(event.target.value)}
                isDisabled={submission === "submitting"}
                variant="filled"
                focusBorderColor="accent"
                bg="surfaceMuted"
                color="textPrimary"
                _placeholder={{ color: "textSecondary" }}
              />
          <Button
            type="submit"
            bg="#fe4155"
            _hover={{ bg: "#ff6271" }}
            _active={{ bg: "#d82d44" }}
            color="white"
            px={8}
            isDisabled={!canSubmit}
            isLoading={submission === "submitting"}
          >
            Start extraction
          </Button>
            </Stack>
          </Box>

          {globalError ? (
            <Alert status="error" mt={6} borderRadius="md">
              <AlertIcon />
              <AlertDescription>{globalError}</AlertDescription>
            </Alert>
          ) : null}

          {job ? (
            <Box mt={8}>
              <Stack spacing={4} bg="surfaceMuted" borderRadius="lg" p={6} borderWidth="1px" borderColor="whiteAlpha.100">
                <Flex align="center" justify="space-between" flexWrap="wrap" gap={3}>
                  <Stack spacing={0}>
                    <Text fontSize="sm" color="textSecondary" textTransform="uppercase" letterSpacing="wide">
                      Current job
                    </Text>
                    <Flex align="center" gap={3} wrap="wrap">
                      {statusBadge}
                      {job.status === "running" ? (
                        <Flex align="center" gap={2}>
                          <Spinner size="sm" color="#fe4155" speed="0.6s" />
                          <Text fontSize="sm" color="textSecondary">
                            Ripping in progress…
                          </Text>
                        </Flex>
                      ) : job.status === "failed" ? (
                        <Text fontSize="sm" color="textSecondary">
                          Rip failed — review the error below.
                        </Text>
                      ) : job.status === "succeeded" ? (
                        <Text fontSize="sm" color="textSecondary">
                          Rip complete — download available below.
                        </Text>
                      ) : null}
                    </Flex>
                  </Stack>
                  <Button
                    variant="outline"
                    borderColor="#fe4155"
                    color="#fe4155"
                    _hover={{ bg: "rgba(254,65,85,0.1)" }}
                    onClick={handleClearJob}
                  >
                    Clear current job
                  </Button>
                </Flex>

                <Box>
                  <Text fontSize="sm" color="textSecondary" textTransform="uppercase" letterSpacing="wide">
                    Source
                  </Text>
                  <Link href={job.theme_url} color="accent" isExternal>
                    {job.theme_url}
                  </Link>
                </Box>

                {expiresAt ? (
                  <Text fontSize="sm" color="textSecondary">
                    Download link {isExpired ? "expired" : "expires"} {expiresLabel}
                  </Text>
                ) : null}

                {job.error ? (
                  <Alert status="error" borderRadius="md">
                    <AlertIcon />
                    <AlertDescription>{job.error}</AlertDescription>
                  </Alert>
                ) : null}
                {isExpired && job.status === "succeeded" ? (
                  <Alert status="warning" borderRadius="md">
                    <AlertIcon />
                    <AlertDescription>
                      This archive has expired. Start a new job to generate a fresh download.
                    </AlertDescription>
                  </Alert>
                ) : null}
                {jobError ? (
                  <Alert status="warning" borderRadius="md">
                    <AlertIcon />
                    <AlertDescription>Status polling failed: {jobError}</AlertDescription>
                  </Alert>
                ) : null}
              </Stack>

              {job.status === "succeeded" ? (
                <Box mt={8}>
                  <Heading size="sm" color="textSecondary" textTransform="uppercase" letterSpacing="wide" mb={3}>
                    Download
                  </Heading>
                  <Stack direction={{ base: "column", sm: "row" }} spacing={4} align={{ base: "stretch", sm: "center" }}>
                    <Button
                      as={Link}
                      href={downloadAvailable ? job?.download_url ?? undefined : undefined}
                      bg="#fe4155"
                      _hover={{ bg: "#ff6271" }}
                      _active={{ bg: "#d82d44" }}
                      color="white"
                      px={8}
                      isExternal
                      isDisabled={!downloadAvailable}
                    >
                      {isExpired ? "Download expired" : "Download zip"}
                    </Button>
                    {expiresAt ? (
                      <Text fontSize="sm" color="textSecondary">
                        Link {isExpired ? "expired" : "expires"} {expiresLabel}
                      </Text>
                    ) : null}
                  </Stack>
                  {isExpired ? (
                    <Alert status="warning" borderRadius="md" mt={3}>
                      <AlertIcon />
                      <AlertDescription>
                        This archive has expired. Start a new job to generate a fresh download.
                      </AlertDescription>
                    </Alert>
                  ) : null}
                </Box>
              ) : null}
            </Box>
          ) : (
            <Box
              mt={8}
              borderRadius="lg"
              borderWidth="1px"
              borderColor="whiteAlpha.100"
              p={8}
              textAlign="center"
              color="textSecondary"
              bg="surfaceMuted"
            >
              Submit a ThemeForest item URL to begin ripping the preview site.
            </Box>
          )}

          {/* Job logs hidden for now */}

        </Box>
      </Container>

      <Box mt={8} textAlign="center">
        <Button
          as={Link}
          leftIcon={<FaGithub />}
          href="https://github.com/aG00Dtime/ThemeForest-Ripper"
          variant="ghost"
          color="textSecondary"
          _hover={{ color: "#fe4155", bg: "rgba(254,65,85,0.08)" }}
          isExternal
        >
          View source on GitHub
        </Button>
      </Box>
    </Box>
  );
}

