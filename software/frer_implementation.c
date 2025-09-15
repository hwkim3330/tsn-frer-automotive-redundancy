/*
 * FRER (Frame Replication and Elimination for Reliability) Implementation
 * IEEE 802.1CB Compliant
 * 
 * Copyright (C) 2025 TSN Research Team
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/netdevice.h>
#include <linux/skbuff.h>
#include <linux/if_ether.h>
#include <linux/if_vlan.h>
#include <linux/hashtable.h>
#include <linux/spinlock.h>
#include <linux/timer.h>

#define FRER_RTAG_ETHERTYPE    0x891D
#define FRER_HISTORY_SIZE      64
#define FRER_MAX_STREAMS       256
#define FRER_RESET_TIMEOUT_MS  1000

/* FRER R-TAG Header Structure */
struct frer_rtag {
    __be16 tci;           /* Tag Control Information */
    __be16 sequence_num;  /* Sequence Number */
} __packed;

/* FRER Stream Context */
struct frer_stream {
    u16 stream_id;
    u16 sequence_counter;     /* For SGF */
    u16 sequence_history[FRER_HISTORY_SIZE]; /* For SRF */
    u16 history_head;
    u16 history_count;
    unsigned long reset_timeout;
    bool sgf_enabled;
    bool srf_enabled;
    spinlock_t lock;
    struct timer_list reset_timer;
};

/* Global FRER context */
static struct frer_stream streams[FRER_MAX_STREAMS];
static DEFINE_SPINLOCK(frer_lock);

/* Stream ID extraction from packet */
static u16 frer_extract_stream_id(struct sk_buff *skb)
{
    struct ethhdr *eth;
    struct vlan_hdr *vhdr;
    
    eth = eth_hdr(skb);
    
    /* Check for VLAN tag */
    if (eth->h_proto == htons(ETH_P_8021Q)) {
        vhdr = (struct vlan_hdr *)(skb->data + ETH_HLEN);
        return ntohs(vhdr->h_vlan_TCI) & VLAN_VID_MASK;
    }
    
    /* Default stream ID based on MAC address */
    return (eth->h_dest[4] << 8) | eth->h_dest[5];
}

/* Reset timeout callback */
static void frer_reset_timeout(struct timer_list *t)
{
    struct frer_stream *stream = from_timer(stream, t, reset_timer);
    unsigned long flags;
    
    spin_lock_irqsave(&stream->lock, flags);
    
    /* Reset sequence history */
    memset(stream->sequence_history, 0, sizeof(stream->sequence_history));
    stream->history_head = 0;
    stream->history_count = 0;
    
    printk(KERN_INFO "FRER: Stream %u reset timeout\n", stream->stream_id);
    
    spin_unlock_irqrestore(&stream->lock, flags);
}

/* Sequence Generation Function (SGF) */
static int frer_sgf_process(struct sk_buff *skb, u16 stream_id)
{
    struct frer_stream *stream = &streams[stream_id];
    struct frer_rtag *rtag;
    struct sk_buff *dup_skb;
    unsigned long flags;
    
    if (!stream->sgf_enabled)
        return 0;
    
    spin_lock_irqsave(&stream->lock, flags);
    
    /* Add R-TAG header */
    rtag = (struct frer_rtag *)skb_push(skb, sizeof(*rtag));
    rtag->tci = htons(FRER_RTAG_ETHERTYPE);
    rtag->sequence_num = htons(++stream->sequence_counter);
    
    spin_unlock_irqrestore(&stream->lock, flags);
    
    /* Create duplicate for redundant path */
    dup_skb = skb_clone(skb, GFP_ATOMIC);
    if (dup_skb) {
        /* Mark duplicate for different egress port */
        dup_skb->mark = 1;
        
        /* Queue duplicate packet */
        dev_queue_xmit(dup_skb);
        
        printk(KERN_DEBUG "FRER SGF: Generated duplicate frame seq=%u\n", 
               ntohs(rtag->sequence_num));
    }
    
    return 0;
}

/* Sequence Recovery Function (SRF) */
static int frer_srf_process(struct sk_buff *skb, u16 stream_id)
{
    struct frer_stream *stream = &streams[stream_id];
    struct frer_rtag *rtag;
    u16 seq_num;
    unsigned long flags;
    int i, is_duplicate = 0;
    
    if (!stream->srf_enabled)
        return 0;
    
    /* Check for R-TAG */
    if (skb->len < sizeof(struct frer_rtag))
        return 0;
    
    rtag = (struct frer_rtag *)skb->data;
    if (ntohs(rtag->tci) != FRER_RTAG_ETHERTYPE)
        return 0;
    
    seq_num = ntohs(rtag->sequence_num);
    
    spin_lock_irqsave(&stream->lock, flags);
    
    /* Check for duplicate in history */
    for (i = 0; i < stream->history_count; i++) {
        if (stream->sequence_history[i] == seq_num) {
            is_duplicate = 1;
            break;
        }
    }
    
    if (is_duplicate) {
        spin_unlock_irqrestore(&stream->lock, flags);
        
        /* Drop duplicate frame */
        kfree_skb(skb);
        
        printk(KERN_DEBUG "FRER SRF: Eliminated duplicate seq=%u\n", seq_num);
        return -1;
    }
    
    /* Add to history */
    stream->sequence_history[stream->history_head] = seq_num;
    stream->history_head = (stream->history_head + 1) % FRER_HISTORY_SIZE;
    if (stream->history_count < FRER_HISTORY_SIZE)
        stream->history_count++;
    
    /* Reset timeout timer */
    mod_timer(&stream->reset_timer, 
              jiffies + msecs_to_jiffies(FRER_RESET_TIMEOUT_MS));
    
    spin_unlock_irqrestore(&stream->lock, flags);
    
    /* Remove R-TAG header */
    skb_pull(skb, sizeof(*rtag));
    
    printk(KERN_DEBUG "FRER SRF: Accepted frame seq=%u\n", seq_num);
    return 0;
}

/* Main FRER processing function */
int frer_process_frame(struct sk_buff *skb, int direction)
{
    u16 stream_id;
    int ret = 0;
    
    stream_id = frer_extract_stream_id(skb);
    if (stream_id >= FRER_MAX_STREAMS)
        return 0;
    
    if (direction == 0) {  /* Ingress - apply SRF */
        ret = frer_srf_process(skb, stream_id);
    } else {              /* Egress - apply SGF */
        ret = frer_sgf_process(skb, stream_id);
    }
    
    return ret;
}

/* Stream configuration interface */
static ssize_t frer_stream_config_write(struct file *file, 
                                       const char __user *buf,
                                       size_t count, loff_t *ppos)
{
    char config[128];
    u16 stream_id;
    int sgf_enable, srf_enable;
    
    if (count >= sizeof(config))
        return -EINVAL;
    
    if (copy_from_user(config, buf, count))
        return -EFAULT;
    
    config[count] = '\0';
    
    if (sscanf(config, "%hu,%d,%d", &stream_id, &sgf_enable, &srf_enable) != 3)
        return -EINVAL;
    
    if (stream_id >= FRER_MAX_STREAMS)
        return -EINVAL;
    
    /* Configure stream */
    streams[stream_id].stream_id = stream_id;
    streams[stream_id].sgf_enabled = !!sgf_enable;
    streams[stream_id].srf_enabled = !!srf_enable;
    streams[stream_id].sequence_counter = 0;
    streams[stream_id].history_head = 0;
    streams[stream_id].history_count = 0;
    
    /* Initialize timer */
    timer_setup(&streams[stream_id].reset_timer, frer_reset_timeout, 0);
    
    printk(KERN_INFO "FRER: Configured stream %u (SGF=%d, SRF=%d)\n",
           stream_id, sgf_enable, srf_enable);
    
    return count;
}

static const struct file_operations frer_config_fops = {
    .write = frer_stream_config_write,
};

/* Module initialization */
static int __init frer_init(void)
{
    int i;
    
    printk(KERN_INFO "FRER: Initializing IEEE 802.1CB implementation\n");
    
    /* Initialize all streams */
    for (i = 0; i < FRER_MAX_STREAMS; i++) {
        spin_lock_init(&streams[i].lock);
        streams[i].stream_id = i;
        streams[i].sgf_enabled = false;
        streams[i].srf_enabled = false;
    }
    
    /* Create sysfs interface */
    proc_create("frer_config", 0666, NULL, &frer_config_fops);
    
    return 0;
}

/* Module cleanup */
static void __exit frer_exit(void)
{
    int i;
    
    /* Clean up timers */
    for (i = 0; i < FRER_MAX_STREAMS; i++) {
        if (streams[i].sgf_enabled || streams[i].srf_enabled) {
            del_timer_sync(&streams[i].reset_timer);
        }
    }
    
    remove_proc_entry("frer_config", NULL);
    
    printk(KERN_INFO "FRER: Module unloaded\n");
}

module_init(frer_init);
module_exit(frer_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("TSN Research Team");
MODULE_DESCRIPTION("IEEE 802.1CB FRER Implementation");
MODULE_VERSION("1.0");

/* Export symbols for other modules */
EXPORT_SYMBOL(frer_process_frame);