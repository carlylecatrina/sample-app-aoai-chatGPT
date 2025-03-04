import { useMemo } from "react";
import { Stack } from "@fluentui/react";

import styles from "./Answer.module.css";

import { Sparkle28Filled, ThumbLike20Filled, ThumbDislike20Filled } from "@fluentui/react-icons";

import { AskResponse, FeedbackString, DocumentResult } from "../../api";
import { parseAnswerToJsx } from "./AnswerParser";

interface Props {
    answer: AskResponse;
    onCitationClicked: (citedDocument: DocumentResult) => void;
    onThoughtProcessClicked: () => void;
    onSupportingContentClicked: () => void;
    onLikeResponseClicked: () => void;
    onDislikeResponseClicked: () => void;
}

export const Answer = ({
    answer,
    onCitationClicked,
    onLikeResponseClicked,
    onDislikeResponseClicked
}: Props) => {
    const parsedAnswer = useMemo(() => parseAnswerToJsx(answer, onCitationClicked), [answer]);

    return (
        <>
            <Stack className={styles.answerContainer} verticalAlign="space-between">
                <Stack.Item>
                    <Stack horizontal horizontalAlign="space-between">
                        <Sparkle28Filled aria-hidden="true" aria-label="Answer logo" />
                        <div>
                            <ThumbLike20Filled
                                aria-hidden="false"
                                aria-label="Like this response"
                                onClick={() => onLikeResponseClicked()}
                                style={answer.feedback == FeedbackString.ThumbsUp ? { color: "darkgreen" } : { color: "slategray" }}
                            />
                            <ThumbDislike20Filled
                                aria-hidden="false"
                                aria-label="Dislike this response"
                                onClick={() => onDislikeResponseClicked()}
                                style={answer.feedback == FeedbackString.ThumbsDown ? { color: "darkred" } : { color: "slategray" }}
                            />
                        </div>
                    </Stack>
                </Stack.Item>

                <Stack.Item grow>
                    <p className={styles.answerText}>{parsedAnswer.answerJsx}</p>
                </Stack.Item>

                {!!parsedAnswer.citations.length && (
                    <Stack.Item>
                        <Stack horizontal wrap className={styles.citationsList} tokens={{ childrenGap: 5 }}>
                            <span className={styles.citationLearnMore}>Citations:</span>
                            {parsedAnswer.citations.map((x, i) => {
                                return (
                                    <a key={i} className={styles.citation} title={x.filepath ?? ""} onClick={() => onCitationClicked(x)}>
                                        {`${++i}${x.filepath ? ". " + x.filepath : ""}`}
                                    </a>
                                );
                            })}
                        </Stack>
                    </Stack.Item>
                )}
            </Stack>
        </>
    );
};
