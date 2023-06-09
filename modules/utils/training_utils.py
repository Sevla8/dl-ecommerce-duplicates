from tqdm import tqdm
import numpy as np
import torch
from matplotlib import pyplot as plt
from modules.utils.AverageMeter import AverageMeter
import gc

def train_func(train_loader, model, criterion, optimizer, device, debug=False):
	model.train()
	bar = tqdm(train_loader)
	losses = []
	for batch_idx, (images, targets) in enumerate(bar):

		images, targets = images.to(device), targets.to(device).long()

		if debug and batch_idx == 100:
			print('Debug Mode. Only train on first 100 batches.')
			break

		logits = model(images, targets)
		loss = criterion(logits, targets)
		loss.backward()
		optimizer.step()
		optimizer.zero_grad()

		losses.append(loss.item())
		smooth_loss = np.mean(losses[-30:])

		bar.set_description(f'loss: {loss.item():.5f}, smth: {smooth_loss:.5f}')

	loss_train = np.mean(losses)
	return loss_train

def valid_func(valid_loader, model, criterion, device):
	model.eval()
	bar = tqdm(valid_loader)

	PROB = []
	TARGETS = []
	losses = []
	PREDS = []

	with torch.no_grad():
		for batch_idx, (images, targets) in enumerate(bar):

			images, targets = images.to(device), targets.to(device).long()

			logits = model(images, targets)

			PREDS += [torch.argmax(logits, 1).detach().cpu()]
			TARGETS += [targets.detach().cpu()]

			loss = criterion(logits, targets)
			losses.append(loss.item())

			bar.set_description(f'loss: {loss.item():.5f}')

	PREDS = torch.cat(PREDS).cpu().numpy()
	TARGETS = torch.cat(TARGETS).cpu().numpy()
	accuracy = (PREDS==TARGETS).mean()

	loss_valid = np.mean(losses)
	return loss_valid, accuracy

def generate_test_features(test_loader, model, device):
	model.eval()
	bar = tqdm(test_loader)

	FEAS = []
	TARGETS = []

	with torch.no_grad():
		for batch_idx, (images) in enumerate(bar):

			images = images.to(device)

			features = model(images)

			FEAS += [features.detach().cpu()]

	FEAS = torch.cat(FEAS).cpu().numpy()

	return FEAS

def row_wise_f1_score(labels, preds):
	scores = []
	for label, pred in zip(labels, preds):
		n = len(np.intersect1d(label, pred))
		score = 2 * n / (len(label) + len(pred))
		scores.append(score)
	return scores, np.mean(scores)

def find_threshold(df, lower_count_thresh, upper_count_thresh, search_space, FEAS):
	score_by_threshold = []
	best_score = 0
	best_threshold = -1
	for i in tqdm(search_space):
		sim_thresh = i/100
		selection = ((FEAS@FEAS.T) > sim_thresh).cpu().numpy()
		matches = []
		oof = []
		for row in selection:
			oof.append(df.iloc[row].posting_id.tolist())
			matches.append(' '.join(df.iloc[row].posting_id.tolist()))
		tmp = df.groupby('label_group').posting_id.agg('unique').to_dict()
		df['target'] = df.label_group.map(tmp)
		scores, score = row_wise_f1_score(df.target, oof)
		df['score'] = scores
		df['oof'] = oof

		selected_score = df.query(f'count > {lower_count_thresh} and count < {upper_count_thresh}').score.mean()
		score_by_threshold.append(selected_score)
		if selected_score > best_score:
			best_score = selected_score
			best_threshold = i

	plt.title(f'Threshold Finder for count in [{lower_count_thresh},{upper_count_thresh}].')
	plt.plot(score_by_threshold)
	plt.axis('off')
	plt.show()
	print(f'Best score is {best_score} and best threshold is {best_threshold/100}')
    
def train_fn(dataloader,model,criterion,optimizer,device,scheduler,epoch):
    model.mode_train = True
    model.train()

    loss_score = AverageMeter()

    tk0 = tqdm(enumerate(dataloader), total=len(dataloader))
    for bi,d in tk0:

        batch_size = d[0].shape[0]

        input_ids = d[0]
        attention_mask = d[1]
        targets = d[2]

        input_ids = input_ids.to(device)
        attention_mask = attention_mask.to(device)
        targets = targets.to(device)

        optimizer.zero_grad()

        output = model(input_ids,attention_mask,targets)

        loss = criterion(output,targets)

        loss.backward()
        optimizer.step()

        loss_score.update(loss.detach().item(), batch_size)
        tk0.set_postfix(Train_Loss=loss_score.avg,Epoch=epoch,LR=optimizer.param_groups[0]['lr'])

        if scheduler is not None:
                scheduler.step()

    return loss_score


def valid_fn(dataloader,model,criterion):
    model.eval()
    model.mode_train = False
    embeds = []
    losses = []
    # loss_score = AverageMeter()

    with torch.no_grad():
        for input_ids, attention_mask,labels in tqdm(dataloader): 
            input_ids = input_ids.cuda()
            attention_mask = attention_mask.cuda()
            labels = labels.cuda()
            feat,outputs = model(input_ids, attention_mask,labels)
            text_embeddings = feat.detach().cpu().numpy()
            embeds.append(text_embeddings)

            # Compute the validation loss
            loss = criterion(outputs, labels)
            losses.append(loss.item())
            # loss_score.update(loss.detach().item(), 32)

    loss_valid = np.mean(losses)
    text_embeddings = np.concatenate(embeds)
    # print(f'Our text embeddings shape is {text_embeddings.shape}')
    del embeds
    gc.collect()
    return text_embeddings,loss_valid


def train_and_valid_fn(trainloader,validloader,model,criterion,optimizer,device,scheduler,epoch):
    model.mode_train = True
    model.train()

    train_loss_score = AverageMeter()

    tk0 = tqdm(enumerate(trainloader), total=len(trainloader))
    for bi,d in tk0:

        batch_size = d[0].shape[0]

        input_ids = d[0]
        attention_mask = d[1]
        targets = d[2]

        input_ids = input_ids.to(device)
        attention_mask = attention_mask.to(device)
        targets = targets.to(device)

        optimizer.zero_grad()

        output = model(input_ids,attention_mask,targets)

        loss = criterion(output,targets)

        loss.backward()
        optimizer.step()

        train_loss_score.update(loss.detach().item(), batch_size)
        tk0.set_postfix(Train_Loss=train_loss_score.avg,Epoch=epoch,LR=optimizer.param_groups[0]['lr'])

        if scheduler is not None:
                scheduler.step()

    # return train_loss_score


    model.eval()
    model.mode_train = False
    embeds = []
    losses = []
    # loss_score = AverageMeter()

    with torch.no_grad():
        for input_ids, attention_mask,labels in tqdm(validloader): 
            input_ids = input_ids.cuda()
            attention_mask = attention_mask.cuda()
            labels = labels.cuda()
            feat,output = model(input_ids, attention_mask,None)
            text_embeddings = feat.detach().cpu().numpy()
            embeds.append(text_embeddings)

            # Compute the validation loss
            loss = criterion(output, labels)
            losses.append(loss.item())
            # loss_score.update(loss.detach().item(), 32)

    valid_loss_score = np.mean(losses)
    text_embeddings = np.concatenate(embeds)
    # print(f'Our text embeddings shape is {text_embeddings.shape}')
    del embeds
    gc.collect()
    return text_embeddings,train_loss_score,valid_loss_score

def train_triplet_fn(dataloader,model,criterion,optimizer,device,scheduler,epoch):
    model.mode_train = True
    model.train()

    loss_score = AverageMeter()

    tk0 = tqdm(enumerate(dataloader), total=len(dataloader))
    for bi,d in tk0:

        batch_size = d[0].shape[0]

        anchor_input_ids, anchor_attention_mask = d[0],d[1]
        positive_input_ids, positive_attention_mask = d[2],d[3]
        negative_input_ids, negative_attention_mask = d[4],d[5]
        targets = d[6]

        anchor_input_ids = anchor_input_ids.to(device)
        anchor_attention_mask = anchor_attention_mask.to(device)
        positive_input_ids = positive_input_ids.to(device)
        positive_attention_mask = positive_attention_mask.to(device)
        negative_input_ids = negative_input_ids.to(device)
        negative_attention_mask = negative_attention_mask.to(device)
        targets = targets.to(device)

        optimizer.zero_grad()

        anchor = model(anchor_input_ids,anchor_attention_mask,targets)
        positive = model(positive_input_ids,positive_attention_mask,targets)
        negative = model(negative_input_ids,negative_attention_mask,targets)

        loss = criterion(anchor,positive,negative)

        loss.backward()
        optimizer.step()

        loss_score.update(loss.detach().item(), batch_size)
        tk0.set_postfix(Train_Loss=loss_score.avg,Epoch=epoch,LR=optimizer.param_groups[0]['lr'])

        if scheduler is not None:
                scheduler.step()

    return loss_score

def valid_triplet_fn(dataloader,model,criterion,device):
    model.eval()
    model.mode_train = False
    embeds = []
    loss_score = AverageMeter()

    with torch.no_grad():
        tk0 = tqdm(enumerate(dataloader), total=len(dataloader))
        for bi,d in tk0:

            batch_size = d[0].shape[0]

            anchor_input_ids, anchor_attention_mask = d[0],d[1]
            positive_input_ids, positive_attention_mask = d[2],d[3]
            negative_input_ids, negative_attention_mask = d[4],d[5]
            targets = d[6]

            anchor_input_ids = anchor_input_ids.to(device)
            anchor_attention_mask = anchor_attention_mask.to(device)
            positive_input_ids = positive_input_ids.to(device)
            positive_attention_mask = positive_attention_mask.to(device)
            negative_input_ids = negative_input_ids.to(device)
            negative_attention_mask = negative_attention_mask.to(device)
            targets = targets.to(device)

            feat,anchor = model(anchor_input_ids,anchor_attention_mask,targets)
            text_embeddings = feat.detach().cpu().numpy()
            embeds.append(text_embeddings)

            _,positive = model(positive_input_ids,positive_attention_mask,targets)
            _,negative = model(negative_input_ids,negative_attention_mask,targets)

            loss = criterion(anchor,positive,negative)

            loss_score.update(loss.detach().item(), batch_size)
    text_embeddings = np.concatenate(embeds)
    print(f'validation loss is  {loss_score.val}')
    # print(f'Our text embeddings shape is {text_embeddings.shape}')
    del embeds
    gc.collect()
    return text_embeddings,loss_score